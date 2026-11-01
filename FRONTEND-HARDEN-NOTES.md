# 前端请求体验加固说明（2026-10-29）

## 超时选择
- **默认超时：30 秒**（`API_TIMEOUT_MS = 30000`）
- 原值 120s 过长，失败感知慢；20–30s 为验收建议区间。取 30s：兼顾代理偶发延迟与「尽快失败可重试」，避免误杀正常慢接口。

## 改动文件
- `web/app.js`（唯一业务改动）
  - `api()` / `apiSignal()`：默认 `AbortSignal.timeout(30000)`；页面 render 期间自动合并 `state.renderSignal`
  - `render()`：新 render 时 `abort()` 上一轮；`catch` 忽略 `AbortError` / 过期 `renderId` / `401`；超时与其它失败写 `#main` errorBox +「重新加载」
  - `401`：调用 `boot()` 前若 `#main` 仍为「正在加载…」则先清空
- `FRONTEND-HARDEN-NOTES.md`（本说明）
- 未改：`workflows.js` / `workspace.js`（`reportView` / `eventDetail` 失败已上抛至 `render` catch）；未改服务端、env、DeepSeek

## 自测要点（对照 AC）

### AC-1 超时
1. DevTools → Network 对 `api/events/{id}` 或 `api/report` 选「Block」或 throttle 至 >30s
2. 打开 `#event/{id}` 或 `#report`
3. 期望：约 30s 后 `#main` 出现 errorBox（超时文案）+「重新加载」；不残留「正在加载…」；不依赖仅 toast

### AC-2 401 / 未登录
1. 清除 Cookie `risk_rag_session`（或使之失效）后访问 `#report` / `#event/25`
2. 期望：loading 结束；进入登录墙或未登录态；`#main` 不永久「正在加载…」

### AC-3 Abort / 竞态
1. 打开 `#report`，在加载中快速切到其它导航再切回
2. 期望：最终 DOM 与当前 hash 一致；过期请求被 abort，不覆盖新页

### AC-4 正常路径回归
1. 登录态打开 `#event/25` → 摘要/影响/建议/来源可见
2. `#report?demo=real` → 简报内容与打印/保存 PDF 入口可见
3. Network 记录状态码与耗时；会话 Cookie 名 `risk_rag_session`

### AC-5 发版
- 本快照仅本地源码；由运维发版后测试按 AC-1～4 复测。
