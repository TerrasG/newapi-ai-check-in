#!/usr/bin/env bash
# AgentKB 服务器兜底签到脚本（带失败重试）
# 用法: ./tools/server_checkin.sh [provider_list]
# 默认: huan666,x666
# 失败时自动重试（最多 MAX_RETRIES 次，间隔 RETRY_DELAY 秒），提高 cron 可靠性
# 环境变量从 .env 注入（不写进脚本，避免敏感值落盘）

set -u
cd "$(dirname "$0")/.." || exit 1

# 通过环境变量注入配置
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
: "${PROXY:?需要设置 PROXY}"

PROVIDERS="${1:-huan666,x666}"
MAX_RETRIES="${CHECKIN_MAX_RETRIES:-3}"
RETRY_DELAY="${CHECKIN_RETRY_DELAY:-60}"

export PYTHONIOENCODING=utf-8
export REQUIRED_PROVIDERS="$PROVIDERS"

run_checkin() {
    echo "[$(date '+%F %T')] 开始签到 providers=$PROVIDERS (attempt $1/$MAX_RETRIES)"
    .venv/bin/python -u main.py
    return $?
}

attempt=1
run_checkin "$attempt"
exit_code=$?

# 失败时重试（跳过偶发网络/授权点击超时）
while [ "$exit_code" -ne 0 ] && [ "$attempt" -lt "$MAX_RETRIES" ]; do
    attempt=$((attempt + 1))
    echo "[$(date '+%F %T')] 签到失败 (exit=$exit_code)，${RETRY_DELAY}s 后重试 ($attempt/$MAX_RETRIES)..."
    sleep "$RETRY_DELAY"
    run_checkin "$attempt"
    exit_code=$?
done

echo "[$(date '+%F %T')] 签到结束 exit_code=$exit_code (attempt $attempt/$MAX_RETRIES)"
exit $exit_code
