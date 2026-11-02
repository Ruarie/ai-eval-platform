#!/usr/bin/env bash
# 用现成镜像跑仓库自带单测（不污染宿主机 Python 环境）。
#
# 关键点：必须把**整个仓库**挂到同一路径，因为部分契约测试会按
# `parents[2] / "docker-compose.yml"`、`frontend/nginx.conf` 读取仓库根文件；
# 只挂 backend/ 会让 ROOT 落到 "/" 从而 4 个用例假失败。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PIP_INDEX="${PIP_INDEX:-https://mirrors.tencent.com/pypi/simple}"

run() {
  local image="$1" workdir="$2" label="$3"
  echo "=== ${label} ==="
  docker run --rm --entrypoint sh \
    -v "${REPO}:/repo" \
    -w "${workdir}" \
    -e PYTHONPATH=.:..:/repo/tools/harness-ws-probe \
    "${image}" \
    -c "pip install -q pytest httpx pytest-asyncio -i ${PIP_INDEX} >/dev/null 2>&1; python -m pytest -q -p no:cacheprovider"
}

run ai-eval-platform-api:latest /repo/backend/api "api pytest"
run ai-eval-platform-worker:latest /repo/backend/worker "worker pytest"
