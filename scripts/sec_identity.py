"""SEC EDGAR fair-access identity (https://www.sec.gov/os/accessing-edgar-data).

SEC asks automated clients to declare who they are with a contact email in the User-Agent; requests without one
are refused with HTTP 403. The contact lives in the GitHub secret SEC_USER_AGENT (e.g. "MyAlphaView research
name@example.com") so it never appears in this public repository or in any generated artifact. An unset or empty
value (the secret not yet added, or a fork) falls back to the previous identity, so behaviour is unchanged until the
Owner adds it. Never log or persist the returned value."""
import os

FALLBACK = "MyAlphaView/6.9 research-agent myalphaview.com"


def user_agent():
    value = (os.getenv("SEC_USER_AGENT") or "").strip()
    return value if "@" in value and len(value) <= 200 else FALLBACK


def configured():
    """True when a contact identity is configured (for status only; the value itself is never exposed)."""
    return user_agent() != FALLBACK
