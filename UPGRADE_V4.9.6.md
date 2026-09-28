# V4.9.6 · Individual Stock Research Card + Operation Extraction

## 本版目标
把 BrightLine 方法从“知识卡”推进到真实研究流程，同时把作者明确披露的股票/期权具体操作单独提取，供历史复盘参考。

## 个股研究卡
- 私有表 `stock_research_notes`，按登录用户隔离。
- 字段：Edge、Thesis、催化剂、最大风险、失效条件、估值/价格位置、下一步研究方案、下一核验日期。
- Trend Pulse 只作为第二层确认。默认先显示通俗解释，不要求普通投资者理解所有技术指标。
- 右键/手机菜单新增“编辑研究卡”。

## BrightLine 具体操作提取
- 新增 `analysis.operations[]`。
- 只提取原文明示的动作：股票/期权、买卖、价格、执行价、到期日、权利金、仓位/规模、触发与退出条件。
- 缺失字段写“未提供”，禁止模型推断。冲突信息标记“存在歧义/待核验”。
- 文学城新增“具体操作”页，历史操作与当前行情严格分开，不作为买卖建议。
- 已把现有资料中可明确确认的 NOW 145 卖出一半，以及 2025-12-14 小仓试错规则作为结构化历史实例；后者保留原文档位歧义，未编码为正式策略。

## 部署
1. 上传完整项目。
2. 在 Supabase 执行 `202609280001_stock_research_notes.sql`。
3. 运行 `Daily Dashboard Update`。
4. 运行 `Wenxuecity Research Update -> blog`，以后继续按每日计划采集。

## 未改变
- QQQM / VGT / QLD 核心阈值未变。
- Trend Pulse 算法未变。
- 期权定价/Greeks 公式未变。

## Final layout correction
- 匿名访问统计不再作为独立大卡片，占用页面正文空间；现在直接并入最底部 Footer，位于版权/免责声明/邮箱之后，并降低视觉权重。
- 个股观察池桌面端固定为一屏 8 列：名称、最新价/涨跌、Trend Pulse、YTD回撤、RSI、距200MA、策略价/距离、状态。
- 移除桌面端残留的表格最小宽度约束并重置历史横向滚动位置；移动端继续使用卡片布局。
- 修复 `design-v4.8.css` 中历史补丁误写的字面量 `\n`，确保最终覆盖规则可以被浏览器正常解析。

## Hotfix: Wenxuecity collector schema test

- `validate_analysis()` now always returns the five narrative analysis fields plus an `operations` array.
- Updated `tests/test_wenxuecity.py` to validate the new schema explicitly instead of assuming a fixed object length of 5.
- No collector logic, strategy thresholds, Trend Pulse logic, or UI behavior changed in this hotfix.
