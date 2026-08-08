#!/usr/bin/env bash
# AgentKB 服务器兜底签到脚本
# 用法: ./tools/server_checkin.sh [provider_list]
# 默认: huan666（稳定；x666 在 1.6G 内存服务器上负载过重易卡死）
# 环境变量从脚本内注入（不写 .env 文件，避免敏感值落盘）

set -u
cd "$(dirname "$0")/.." || exit 1

# 通过环境变量注入配置（值需在部署时填入，或用外部 env 文件）
# 这里从 /opt/newapi-ai-check-in/.env 读取（若存在），否则要求环境变量
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source ".env"
    set +a
fi

# 必需环境变量检查
: "${ACCOUNTS:?需要设置 ACCOUNTS}"
: "${ACCOUNTS_LINUX_DO:?需要设置 ACCOUNTS_LINUX_DO}"
: "${STORATE_STATES_LINUXDO:?需要设置 STORATE_STATES_LINUXDO}"
# PROXY 需要指向本机 Tailscale 的 Clash 代理
: "${PROXY:?需要设置 PROXY}"

PROVIDERS="${1:-huan666}"

export PYTHONIOENCODING=utf-8
export REQUIRED_PROVIDERS="$PROVIDERS"

echo "[$(date '+%F %T')] 开始签到 providers=$PROVIDERS"
.venv/bin/python -u main.py
exit_code=$?
echo "[$(date '+%F %T')] 签到结束 exit_code=$exit_code"
exit $exit_code
