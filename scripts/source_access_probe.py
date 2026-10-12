#!/usr/bin/env python3
"""Opt-in, read-only probes. No login, proxy bypass, or third-party full-text persistence."""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

UA = "MyAlpha-Research-Probe/1.0"
WXC_HOSTS = {"blog.wenxuecity.com", "bbs.wenxuecity.com"}
VIDEO_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def read_limited(url, max_bytes=300000, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("response_too_large")
        return response.status, body.decode("utf-8", "replace")


def http_reason(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return "http_" + str(exc.code)
    if isinstance(exc, urllib.error.URLError):
        return "network_error"
    return type(exc).__name__


def probe_wxc(url):
    result = {"source": "wenxuecity", "url": url, "status": "FAIL"}
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in WXC_HOSTS or parsed.username or parsed.password:
        return dict(result, reason="invalid_public_wxc_url")
    robots_url = "https://" + parsed.hostname + "/robots.txt"
    try:
        _, robots = read_limited(robots_url, 100000)
        if "<html" in robots.lower():
            return dict(result, reason="robots_unreadable")
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(robots.splitlines())
        if not rp.can_fetch(UA, url):
            return dict(result, status="BLOCKED", reason="robots_disallow")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return dict(result, status="BLOCKED", reason="robots_http_" + str(e.code))
    except Exception as e:
        return dict(result, status="BLOCKED", reason="robots_" + http_reason(e))
    try:
        _, raw = read_limited(url)
        # Existence of HTML is not evidence of a valid article.
        if len(raw.strip()) < 500 or any(s in raw.lower()[:3000] for s in ("captcha", "just a moment", "security verification")):
            return dict(result, status="PARTIAL", reason="short_or_challenge_page")
        result.update(status="PASS", reason="direct_html_received", chars=len(raw))
        return result
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            return dict(result, status="BLOCKED", reason="source_http_" + str(e.code))
        return dict(result, reason="source_http_" + str(e.code))
    except Exception as e:
        return dict(result, reason=http_reason(e))


def probe_youtube(video_id):
    url = "https://www.youtube.com/watch?v=" + video_id
    result = {"source": "youtube", "video_id": video_id, "url": url, "status": "FAIL"}
    exe = shutil.which("yt-dlp")
    if not exe:
        return dict(result, reason="yt_dlp_not_installed")
    with tempfile.TemporaryDirectory(prefix="myalpha-yt-probe-") as temp:
        cmd = [exe, "--no-playlist", "--skip-download", "--write-subs", "--write-auto-subs",
               "--sub-langs", "en.*,zh.*,en,zh", "--sub-format", "vtt/srt/best",
               "--socket-timeout", "12", "--retries", "1", "--extractor-retries", "1",
               "-o", str(Path(temp) / "%(id)s.%(ext)s"), url]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=95, check=False)
        except subprocess.TimeoutExpired:
            return dict(result, reason="yt_dlp_timeout")
        files = list(Path(temp).glob("*.vtt")) + list(Path(temp).glob("*.srt"))
        valid = [p for p in files if p.stat().st_size >= 100]
        if valid:
            return dict(result, status="PASS", reason="subtitle_file_received",
                        subtitle_files=len(valid), subtitle_bytes=sum(p.stat().st_size for p in valid))
        stderr = (p.stderr or "").lower()
        if "sign in" in stderr or "bot" in stderr:
            reason = "youtube_auth_or_bot_challenge"
        elif "429" in stderr:
            reason = "youtube_rate_limited"
        elif "no subtitles" in stderr or "not available" in stderr:
            reason = "no_accessible_subtitles"
        else:
            reason = "yt_dlp_exit_" + str(p.returncode) if p.returncode else "no_subtitle_file"
        return dict(result, reason=reason)


def main():
    parser = argparse.ArgumentParser(description="Controlled public source probes; no uploads or API tokens.")
    parser.add_argument("--wxc-url", default="https://blog.wenxuecity.com/myoverview/82458/")
    parser.add_argument("--youtube-id", default="qVSoCX8pVDg")
    parser.add_argument("--output", help="Optional JSON path for metadata-only report")
    args = parser.parse_args()
    if not VIDEO_RE.fullmatch(args.youtube_id):
        parser.error("Invalid YouTube video ID")
    report = {"schema": "myalpha-source-probe-v1", "tested_at": datetime.now(timezone.utc).isoformat(),
              "production_use": False, "probes": [probe_wxc(args.wxc_url), probe_youtube(args.youtube_id)]}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
