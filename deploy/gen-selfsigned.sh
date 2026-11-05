#!/usr/bin/env bash
# 生成 HTTPS 自签证书（宿主机执行；容器以只读方式挂载，不依赖自定义镜像）。
#
# 生产入口是内网 IP，无法申请公有证书；证书落在 ./data/https，重建容器不换，
# 客户端首次访问会提示不受信任，导入 server.crt 到"受信任的根证书颁发机构"即可消除。
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$APP_DIR/data/https"

read_env() {
  local key="$1" fallback="$2" value
  value="$(awk -F= -v k="$key" '$0 ~ "^"k"=" {print substr($0, index($0,"=")+1)}' "$APP_DIR/.env" 2>/dev/null | tail -1)"
  printf '%s' "${value:-$fallback}"
}

HOST="${HTTPS_HOST:-$(read_env HTTPS_HOST 127.0.0.1)}"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/server.crt" ] && [ -f "$CERT_DIR/server.key" ]; then
  echo "自签证书已存在，跳过：$CERT_DIR/server.crt"
  exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
  -keyout "$CERT_DIR/server.key" -out "$CERT_DIR/server.crt" \
  -subj "/CN=$HOST" -addext "subjectAltName=IP:$HOST,DNS:localhost"
chmod 600 "$CERT_DIR/server.key"
echo "已生成自签证书 CN=$HOST（SAN: IP $HOST, DNS localhost）"
