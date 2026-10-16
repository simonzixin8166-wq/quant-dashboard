# OFI 阶段 A：收盘期权快照与 OI 存档（owner 已批准，#133）

- **审计**：6141895485。**批准**：owner 会话指令 2026-10-13，回执 6142705659。
- **范围**：持仓标的（运行时从 Supabase 读取，仅在私有侧使用）∪ 6 只上下文标的 QQQ SOFI LITE IREN NVDA TSLA。上限 15 只；持仓优先，超出上限时先舍弃上下文标的。
- **过滤窗口**：到期日 ≤ +60 天，行权价在最近本地收盘价 ±20% 以内。没有参考价时不做行权价过滤，也不猜测价格。
- **存储**：私有账本仓库，stream `option_chain_snapshots`，`record_id = ocs:<market_date>:<symbol>`，只追加，带哈希链。公开仓库只写聚合状态文件 `docs/research/option_snapshot_status.json`，其中不含任何标的、合约、持仓或账户信息。
- **数据源**：
  - Alpaca 免费 Basic 的 `feed=indicative`：报价经过调整、成交有延迟，提供 bid、ask、last、当日 volume、IV、delta；
  - `/v2/options/contracts`：提供 OI、`open_interest_date` 和 close_price。OI 通常是前一交易日的数值，每行都保存其日期。
- **Edge Function 新增两个只读 action**：`oi_window` 和 `chain_window`。原有的 expirations / chain / quote 三个 action 行为不变。
- **运行时机**：只在交易日 20:00–24:00 UTC 执行，即 21:30Z 的 Daily。08:15Z 的早间 Daily 会跳过，同一交易日不会重复抓取。手动补跑用 `OFI_SNAPSHOT_FORCE=1`。
- **失败处理（fail-closed）**：
  - 私有账本未配置时，不发起任何请求，状态记为 `unavailable`；
  - 单个标的失败时，该条记为 `status=error`，其余标的照常存档；
  - Daily 中这一步会设置 continue-on-error 并调用失败标记，不阻断网站构建。
- **明确不做**：异常评分、信号、首页展示、下单、付费数据。每行都带 `used_in_decision=false` 和 `signal=null`。

## 请求预算

`calls/day = Σ_i [ pages_oi(i) + pages_chain(i) ] + 2`（最后的 2 次是 Supabase 读持仓）

- 窗口过滤后，通常每个标的 1 页 + 1 页。按 N ≈ 6–10 估算，约 **14–22 次/日**。
- 分页上限：contracts 3 页（每页 10000 条），snapshots 5 页（每页 1000 条）。超过上限时记 `truncated=true`。
- 免费额度与限流：**unknown**，首日运行后以实际 HTTP 状态核对。

## 待实测（首日运行后报告）

- `chain_window` 是否接受 `expiration_date_lte`、`strike_price_gte`、`strike_price_lte` 参数；
- contracts 返回中 `open_interest_date` 的实际滞后；
- indicative 报价的时间戳；
- 窗口过滤后每个标的的合约数。

## 后续

- **阶段 B**：至少积累 20 个交易日、同口径的基线之后才考虑。在此之前不计算任何异常指标。
- **持仓合约本身在窗口外的情形**（例如 LEAPS、远月 CC）：阶段 A 不覆盖，列为缺口。
