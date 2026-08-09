#!/usr/bin/env bash
# AgentKB 服务器健康检查
# 检查: mihomo 代理状态、最近签到是否执行、磁盘/内存是否健康
# 用法: ./tools/server_health_check.sh
# 返回: 0=健康, 1=有异常

set -u
cd "$(dirname "$0")/.." || exit 1

LOG_DIR="logs"
LOG_FILE="$LOG_DIR/server_checkin.log"
ISSUES=0

echo "=== [$(date '+%F %T')] 服务器健康检查 ==="

# 1. mihomo 代理状态
if systemctl is-active --quiet mihomo 2>/dev/null; then
    echo "✅ mihomo 代理: active"
else
    echo "❌ mihomo 代理: 未运行"
    ISSUES=$((ISSUES + 1))
fi

# 2. 最近签到是否执行（检查日志最后修改时间）
if [ -f "$LOG_FILE" ]; then
    LAST_MOD=$(stat -c %Y "$LOG_FILE" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    AGE_HOURS=$(( (NOW - LAST_MOD) / 3600 ))
    echo "✅ 签到日志: $(( AGE_HOURS )) 小时前更新"
    # 超过 30 小时没签到日志（cron 每天 13:37，30h 说明漏跑）
    if [ "$AGE_HOURS" -gt 30 ]; then
        echo "❌ 签到日志超过 30 小时未更新，可能 cron 漏跑"
        ISSUES=$((ISSUES + 1))
    fi
    # 检查最后一次签到是否成功
    LAST_RESULT=$(grep "签到结束 exit_code=" "$LOG_FILE" 2>/dev/null | tail -1)
    echo "   最近结果: ${LAST_RESULT:-无记录}"
else
    echo "❌ 签到日志不存在"
    ISSUES=$((ISSUES + 1))
fi

# 3. 磁盘空间
DISK_USED=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
echo "✅ 磁盘使用: ${DISK_USED}%"
if [ "$DISK_USED" -gt 85 ]; then
    echo "❌ 磁盘使用率过高 (${DISK_USED}%)"
    ISSUES=$((ISSUES + 1))
fi

# 4. 内存
MEM_AVAIL_MB=$(free -m | awk '/^Mem:/ {print $7}')
echo "✅ 可用内存: ${MEM_AVAIL_MB}MB"
if [ "$MEM_AVAIL_MB" -lt 100 ]; then
    echo "❌ 可用内存过低 (${MEM_AVAIL_MB}MB)"
    ISSUES=$((ISSUES + 1))
fi

echo "=== 检查完成: $([ "$ISSUES" -eq 0 ] && echo '健康' || echo "${ISSUES} 项异常") ==="
exit "$ISSUES"
