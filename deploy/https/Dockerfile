# HTTPS 反向代理：nginx + 启动时生成自签证书（内网 IP 无法申请公有证书）。
FROM nginx:1.27-alpine

# 启动脚本用 openssl 生成自签证书，基础镜像不含该命令。
RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY entrypoint-cert.sh /docker-entrypoint.d/40-selfsigned-cert.sh
RUN chmod +x /docker-entrypoint.d/40-selfsigned-cert.sh
