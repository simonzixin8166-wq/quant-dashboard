# AGENTS.md — 给编码代理（Jules 等）的仓库须知

本仓库的产品章程见 `CLAUDE.md`（所有改动都必须遵守）。下面是写代码前必须知道的约定。

## 语言
- **全程使用中文**：计划、进度、最终报告、**PR 标题和 PR 描述**都用中文。代码、命令、日志原文保持原样。

## 绝对禁止
- 不手改生成文件：`docs/index.html`（由 `scripts/fetch_and_build.py` 生成）、`docs/data.json`、`docs/data/**`、`docs/research/**`、`research/**` 下的产物、`data/history/*.zip`。要改页面结构就改 `scripts/fetch_and_build.py` 的模板（Python f-string，花括号写成 `{{ }}`）。
- 不改投资策略阈值、仓位、风控规则、定时计划（cron）、secrets，不加自动交易/下单。
- 不删除、跳过、放宽任何已有测试断言来让 CI 变绿；不提交 `test_output.txt` 之类的临时文件。
- 不删除已有函数或已导出的接口（例如 `window.OptionV2.*`）；需要替换时保留旧函数作为回退。
- 不在全局对象上挂通用名字（如 `window.holidays`）；新前端模块用 `window.MAV<模块名>` 命名空间。

## 代码约定
- `scripts/` **不是 Python 包**：测试里用
  `ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT/'scripts')); import xxx`，不要写 `from scripts import xxx`。
- 新前端资源：在 `scripts/fetch_and_build.py` 模板里加 `<script src="assets/xxx.js?v={ASSET_VERSION}">`，并加入 `scripts/generate_build_manifest.py` 的 `FILES`。
- 前端 JS 是浏览器 IIFE，但会被 Node 测试单独 `require`：文件必须在没有 `window`/`document` 时也能加载（用 `typeof window!=='undefined'?window:globalThis`）。
- 交易日历以 `scripts/trading_calendar.py` 为准；前端用 `docs/assets/trading-calendar.js`（`window.MAVTradingCalendar`）。
- 新测试必须登记到 workflow，否则 CI 不会跑：一般加到 `.github/workflows/v56-pr-validation.yml` 的测试列表。

## 提交前必须运行（并把输出原文贴在报告里）
1. 你改动/新增的测试。
2. 加载了你改动文件的现有测试：`grep -ln "<你改的文件名>" tests/*` 找出来全部运行。
3. 改了 `docs/assets/*.js`：`node --check` 每个文件，并运行 `node tests/pr254_round2_contracts.test.js`、`node tests/options_v2.test.js`、`node tests/option_decision.test.js`。
4. 改了 `scripts/fetch_and_build.py`：`python tests/test_build_contract.py`。
5. 依赖 yfinance 等外部库的测试在无网络时可能失败——说明原因，不要改测试绕过。

## 交付
- 一个任务一个小 PR，只改任务卡列出的文件。
- 报告写清：改了哪些文件、为什么、运行了哪些命令及原始输出。拿不到的数据（如 GitHub Actions 运行记录）标 `UNVERIFIED`，不要猜。
