# V3.9.0 · PWA 第一阶段

- 网站与手机 PWA 继续共用同一套 `docs/` 代码和 Supabase 数据。
- 增加 Web App Manifest、主屏幕图标、独立窗口显示和安装入口。
- 增加安全的离线页面；断网重新打开时直接进入离线说明，不把旧行情或旧持仓伪装成最新数据。
- Service Worker 只缓存页面外壳和静态资源，明确排除 Supabase Auth、数据库与 Edge Function 请求。
- 网站部署新版本后显示“立即更新”，点击后切换到新版；失败时仍保留上一版页面外壳。
- 增加网络中断提示，并兼容 iPhone 安全区域。

## 上传说明

必须完整覆盖上传本压缩包内全部文件，尤其是新增的：

- `docs/manifest.webmanifest`
- `docs/sw.js`
- `docs/offline.html`
- `docs/icons/`
- `docs/assets/pwa.js`
- `docs/assets/pwa.css`

GitHub Pages 部署完成后，首次打开网页刷新一次；支持的浏览器会显示“安装应用”。iPhone 可通过 Safari 分享菜单选择“添加到主屏幕”。
