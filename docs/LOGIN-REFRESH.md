# 登录态刷新 SOP

**目的**: 当签到显示 `authentication_failed` / `Cache session expired` / `auth.session-token` 失效时，刷新 linux.do 登录态并同步到两处（GitHub Secret + 服务器 .env）。

**预计耗时**: 10 分钟内

## 什么时候需要刷新

- 签到日志出现: `Cache session expired, need to login again`
- 结果表: 多个 Provider 同时 `authentication_failed`（登录态共享失效）
- 连续 2 天签到失败

## 前置条件

- 本机 Windows（有 Chrome + 代理）
- 本机代理（Clash）开启
- linux.do 账号密码（`cjh200300` / `1053123738@qq.com`）

## 步骤

### 1. 启动调试 Chrome 并登录 linux.do

```powershell
# 启动带调试端口的 Chrome（独立 profile，不影响日常浏览）
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\tianh\AppData\Local\Temp\linuxdo-login-profile" https://linux.do/login
```

- 在 Chrome 窗口手动登录 linux.do（过 Cloudflare 验证）

### 2. 完成关键站点的 OAuth 授权

登录后在浏览器访问以下授权 URL，**逐个点"允许"**（每个都需完成）:

```
# anyrouter
https://connect.linux.do/oauth2/authorize?response_type=code&client_id=8w2uZtoWH9AUXrZr1qeCEEmvXLafea3c&state=refresh
# huan666
https://connect.linux.do/oauth2/authorize?response_type=code&client_id=FNvJFnlfpfDM2mKDp8HTElASdjEwUriS&state=refresh
# x666
https://connect.linux.do/oauth2/authorize?response_type=code&client_id=4OtAotK6cp4047lgPD4kPXNhWRbRdTw3&state=refresh
```

> **重要**: up.x666.me 的授权也需要（x666 专用），访问:
> `https://connect.linux.do/oauth2/authorize?client_id=p4V7ALyYtjreFlru3Mp5V5enzhpMYxcy&redirect_uri=https%3A%2F%2Fup.x666.me%2Fapi%2Fauth%2Fcallback&response_type=code&scope=read&state=refresh`
> 点"允许"后应跳转到 up.x666.me。

### 3. 导出 storage state

```powershell
cd C:\Users\tianh\Documents\Codex-Contexts\newapi-ai-check-in
.venv\Scripts\python.exe -c "
import os
from playwright.sync_api import sync_playwright
out = os.path.abspath('storage-states/linuxdo_storage_state.json')
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    ctx = b.contexts[0]
    ctx.storage_state(path=out)
    cks = ctx.cookies()
    print('导出', len(cks), 'cookies')
    print('_t:', '有' if any(c['name']=='_t' for c in cks) else '缺失')
    print('connect auth.session-token:', '有' if any(c['name']=='auth.session-token' for c in cks) else '缺失')
    b.close()
"
```

**验证**: 必须同时有 `_t` 和 `auth.session-token`，否则授权不完整，重新做步骤 2。

### 4. 同步到 GitHub Secret

```powershell
python -c "
import json
state = json.load(open('storage-states/linuxdo_storage_state.json', encoding='utf-8'))
value = json.dumps({'1053123738@qq.com': state}, ensure_ascii=False)
open(r'C:\Users\tianh\AppData\Local\Temp\storate_value.json', 'w', encoding='utf-8').write(value)
print('值长度:', len(value))
"
# 用 TerrasG 账号
export GH_TOKEN="$(gh auth token --user TerrasG)"
gh secret set STORATE_STATES_LINUXDO --env production --repo TerrasG/newapi-ai-check-in < C:\Users\tianh\AppData\Local\Temp\storate_value.json
```

### 5. 同步到服务器 .env

```powershell
# 上传最新 storage state
scp storage-states/linuxdo_storage_state.json AgentKB:/opt/newapi-ai-check-in/storage-states/linuxdo_storage_state.json
# 重建服务器 .env（引号包裹，避免 bash source 解析问题）
ssh AgentKB 'cd /opt/newapi-ai-check-in && STORATE_DATA=$(cat storage-states/linuxdo_storage_state.json) && cat > .env <<ENVEOF
ACCOUNTS='"'"'[{"provider":"huan666","linux.do":true},{"provider":"x666","linux.do":true}]'"'"'
ACCOUNTS_LINUX_DO='"'"'[{"username":"1053123738@qq.com","password":"x"}]'"'"'
STORATE_STATES_LINUXDO='"'"'{"1053123738@qq.com": $STORATE_DATA}'"'"'
PROXY='"'"'{"server":"http://127.0.0.1:7897}'"'"'
ENVEOF
chmod 600 .env'
```

### 6. 清理服务器旧缓存并验证

```bash
# 服务器删旧缓存，强制用新登录态
ssh AgentKB 'rm -f /opt/newapi-ai-check-in/storage-states/linuxdo_724b0f52_storage_state.json /opt/newapi-ai-check-in/storage-states/x666_up_*.json'

# 服务器验证（应 success）
ssh AgentKB 'cd /opt/newapi-ai-check-in && ./tools/server_checkin.sh huan666,x666'
```

### 7. GitHub Actions 验证（可选）

触发 workflow_dispatch 在 main 上，确认 Provider 认证成功。

## 常见问题

| 问题 | 处理 |
|---|---|
| 导出时 `_t` 缺失 | linux.do 会话过期，重新登录（步骤 1） |
| `auth.session-token` 缺失 | connect.linux.do 授权没完成，重做步骤 2 |
| 服务器签到仍失败 | 服务器 .env 的 STORATE 值未更新，重做步骤 5 |
| 更新后 Actions 仍失败 | runner IP 与登录态绑定，属已知限制；靠服务器兜底 |

## 频率建议

登录态有效期通常数天到数周。**每周检查一次**签到结果；连续失败才需刷新。
