#!/usr/bin/env bash
# Agent 回答质量巡检：跑固定题库并把结果留档，供每天对比。
#
# 用法：直接执行（cron 也调用它）。依赖 frontend/node_modules 里的 playwright。
# 退出码与题库阈值一致（默认 80% 通过），低于阈值时 cron 邮件/日志能看出来。
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$APP_DIR/data/agent-quality"
mkdir -p "$OUT_DIR"

STAMP="$(date +%Y-%m-%d)"
LOG="$OUT_DIR/$STAMP.log"
HISTORY="$OUT_DIR/history.tsv"

# 只挑需要的键，避免 source 整个 .env（值里可能有空格、# 等 shell 敏感字符）。
read_env() {
  local key="$1" fallback="$2" value
  value="$(awk -F= -v k="$key" '$0 ~ "^"k"=" {print substr($0, index($0,"=")+1)}' "$APP_DIR/.env" 2>/dev/null | tail -1)"
  printf '%s' "${value:-$fallback}"
}

ADMIN_USER="$(read_env BOOTSTRAP_ADMIN_USERNAME admin)"
ADMIN_PASSWORD="$(read_env BOOTSTRAP_ADMIN_PASSWORD '')"
WEB_PORT="$(read_env WEB_PORT 16675)"

export AGENT_QA_BASE_URL="${AGENT_QA_BASE_URL:-http://127.0.0.1:${WEB_PORT}}"
export AGENT_QA_USER="${AGENT_QA_USER:-$ADMIN_USER}"
export AGENT_QA_PASSWORD="${AGENT_QA_PASSWORD:-$ADMIN_PASSWORD}"

if [ -z "$AGENT_QA_PASSWORD" ]; then
  echo "缺少 AGENT_QA_PASSWORD（.env 里的 BOOTSTRAP_ADMIN_PASSWORD 为空）" >&2
  exit 2
fi

cd "$APP_DIR/frontend" || exit 2
node tests/agent-quality/run.mjs >"$LOG" 2>&1
STATUS=$?

SUMMARY="$(grep -E '^SUMMARY ' "$LOG" | tail -1 || true)"
if [ -z "$SUMMARY" ]; then
  SUMMARY="SUMMARY unknown（脚本未产出统计）"
fi

printf '%s\t%s\t%s\n' "$STAMP" "$SUMMARY" "$STATUS" >>"$HISTORY"
echo "$STAMP $SUMMARY exit=$STATUS"

echo "历史留档：$HISTORY"
exit "$STATUS"
