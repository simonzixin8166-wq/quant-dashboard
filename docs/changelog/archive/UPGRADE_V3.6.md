# myAlphaView V3.6.0 私有访问门禁与匿名统计

## 访问控制

- 未登录只展示顶部市场概览与四张核心指标卡。
- 策略引擎、指数、A/H市场、观察池、期权、沙盒、历史归档和数据状态均需主理人登录。
- 只有配置的主理人邮箱可以解锁；其他 Supabase 登录账户会被立即退出。
- 新增 `noindex / nofollow / noarchive` 与 `robots.txt`，降低搜索引擎收录概率。
- 真实期权持仓仍由 Supabase RLS 保护。前端门禁不能替代数据库权限。

## 匿名访问统计

- 同一浏览器每天只计一次。
- 仅保存不可逆匿名哈希、页面路径、来源域名、设备类型和访问时间。
- 不保存 IP 地址、姓名、邮箱或原始浏览器标识。
- 登录后可查看近7日访问、近30日访问、近30日匿名浏览器数和最近访问时间。

## 部署

1. 在 Supabase SQL Editor 执行 `supabase/migrations/202609240004_private_gate_analytics.sql`。
2. 上传完整项目。
3. 在 GitHub Actions 手动运行 `Daily Dashboard Update` 一次。
