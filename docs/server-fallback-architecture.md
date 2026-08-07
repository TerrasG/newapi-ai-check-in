# 服务器兜底签到架构

**日期**: 2026-08-08
**状态**: 已部署并验证（huan666 稳定，服务器自给自足）

## 一、架构总览

```
┌─────────────────────┐      ┌──────────────────────────┐
│ AgentKB 服务器       │      │ 本机（Windows）           │
│ (139.196.40.166)    │      │                          │
│                     │      │                          │
│  cron 每天 13:37    │      │  （仅首次部署时需要）      │
│   └→ server_checkin │      │  Clash 订阅（节点来源）    │
│       └→ main.py    │      │                          │
│           └→ 本地代理 │      │                          │
│              mihomo  │      │                          │
│              :7897   │      │                          │
│               └→ 境外 │      │                          │
│              linux.do│      │                          │
└─────────────────────┘      └──────────────────────────┘
```

**核心改进**: 服务器用 **mihomo 代理**（自装，节点 IP 直连），**不依赖本机**。本机只在首次部署时提供 Clash 订阅节点。

## 二、为什么服务器能开代理（关键洞察）

国内服务器访问境外被墙，但 **mihomo + 节点 IP 直连**可以绕过 DNS 污染：
- 本机 Clash 订阅解析出节点**真实 IP**（DNS 污染的 IP 换成真实 IP）
- 服务器**用 IP 直连**节点（绕过 DNS 污染）
- 实测 39 个节点里 **9 个 IP 服务器可直连**（日本/新加坡/美国节点）

## 三、服务器组件

| 组件 | 位置 | 状态 |
|---|---|---|
| mihomo 代理 | `/usr/local/bin/mihomo` + `/etc/mihomo/config.yaml` | systemd 开机自启 |
| 签到代码 | `/opt/newapi-ai-check-in/` | @ `29fe18d` |
| 签到脚本 | `/opt/newapi-ai-check-in/tools/server_checkin.sh` | 读 `.env` 跑 main.py |
| 凭据 | `/opt/newapi-ai-check-in/.env`（600 权限） | ACCOUNTS/STORATE_STATES/PROXY |
| 签到 cron | `crontab` 每天 13:37 | 跑 huan666 |
| 签到日志 | `/opt/newapi-ai-check-in/logs/server_checkin.log` | 追加式 |

## 四、mihomo 代理配置要点

- 配置: `/etc/mihomo/config.yaml`
- 端口: `mixed-port: 7897`（HTTP/SOCKS 混合）
- 节点: 从本机 Clash 订阅提取的 **27 个可达节点**（`server` 改为**真实 IP**）
- 分组: `Auto`（url-test 自动选延迟最低可用节点）
- 规则: linux.do / connect.linux.do / huan666.de / x666.me / github.com 等走代理
- 启动: `systemctl start mihomo`（enabled 开机自启）

**更新节点**: 本机 Clash 订阅变化时，重新用本机配置生成 `config.yaml` 覆盖 `/etc/mihomo/config.yaml` 并 `systemctl restart mihomo`。

## 五、签到 `.env` 关键变量

```
ACCOUNTS=[{"provider":"huan666","linux.do":true}]
ACCOUNTS_LINUX_DO=[{"username":"...","password":"..."}]
STORATE_STATES_LINUXDO={"<username>": <playwright storage_state>}
PROXY={"server":"http://127.0.0.1:7897"}   # 指向服务器本地 mihomo
```

## 六、验证记录

- ✅ 服务器 mihomo 代理访问 linux.do 返回 403（Cloudflare 正常拦截，网络通）
- ✅ huan666 签到通过本地代理 `status: success, already_done`
- ✅ mihomo systemd 开机自启 enabled
- ✅ cron 每天 13:37 自动跑

## 七、已知边界 / 待办

| 项 | 状态 | 说明 |
|---|---|---|
| **x666 签到** | ⚠️ 脆弱 | 1.6G 内存跑 x666 完整流程（多次 camoufox）会卡死；机制已验证能通，需 ≥4G 内存才稳定。cron 暂只跑 huan666。 |
| **节点过期** | ⚠️ 需更新 | 代理节点来自 Clash 订阅，会过期（当前套餐 2026-09-02 到期），需定期更新 `/etc/mihomo/config.yaml` |
| **GitHub Actions 主路径** | ⏳ 待恢复 | GitHub 平台 major_outage 中，恢复后主路径验收 + PR 合并 |
| **通知渠道** | ⚠️ 未配 | EMAIL/PUSHPLUS 等通知 Secret 未配置，`not_configured` |

## 八、常用运维命令

```bash
# 检查代理
systemctl status mihomo
curl -x http://127.0.0.1:7897 https://linux.do/ -o /dev/null -w "%{http_code}"

# 手动签到
cd /opt/newapi-ai-check-in && ./tools/server_checkin.sh huan666

# 查看签到日志
tail -f /opt/newapi-ai-check-in/logs/server_checkin.log

# 重启 mihomo（改配置后）
systemctl restart mihomo
```
