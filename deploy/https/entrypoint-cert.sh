#!/bin/sh
# 首次启动生成自签证书；证书持久化在 ./data/https，重建容器不换证书。
set -e
CERT_DIR=/etc/nginx/certs
HOST="${HTTPS_HOST:-127.0.0.1}"
mkdir -p "$CERT_DIR"
if [ ! -f "$CERT_DIR/server.crt" ] || [ ! -f "$CERT_DIR/server.key" ]; then
  echo "生成自签证书 CN=$HOST（SAN: IP $HOST, DNS localhost）"
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout "$CERT_DIR/server.key" -out "$CERT_DIR/server.crt" \
    -subj "/CN=$HOST" \
    -addext "subjectAltName=IP:$HOST,DNS:localhost"
  chmod 600 "$CERT_DIR/server.key"
fi
