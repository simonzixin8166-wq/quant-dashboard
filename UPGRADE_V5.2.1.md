
## Hotfix 1 · 2026-09-29

- 修复 `scripts/fetch_and_build.py` 中系统自检（QA）CSS 在 Python f-string 内未转义大括号，导致 `NameError: name 'padding' is not defined`。
- 新增构建契约回归检查，防止 `.qa-empty{...}` 这类未转义 CSS 再次进入 f-string 模板。
- 不修改任何行情源、刷新频率、Supabase 接口、Trend Pulse 算法或投资规则。


## Hotfix 2 — Autonomous QA trigger + assistant selector
- Fix Browser QA assistant selector: the live assistant root is `#marketOptionAlert`, not `#investmentAssistant`.
- Run Autonomous QA automatically after `Daily Dashboard Update` completes successfully via `workflow_run`. GitHub does not start a second workflow from a push made by the default `GITHUB_TOKEN`, so the previous `push`-only design required manual execution.
- Keep `workflow_dispatch` as a manual fallback.
- Upgrade CodeQL action to v4 and pin QA runner to Ubuntu 24.04 to remove the current deprecation warnings where practical.
