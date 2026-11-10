FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.org/simple/ \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

COPY requirements.txt constraints.txt ./
# 下载缓存留在构建器中，依赖更新时复用，不增加运行镜像体积。
# constraints.txt 锁住 lightrag-hku 未锁的传递依赖，保证同一提交构建结果一致。
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt -c constraints.txt

# tiktoken 首次使用会联网下载 BPE 词表；构建期预热到镜像内，运行时离线可用。
# 构建机无外网时预热失败不阻塞镜像，运行期由索引失败状态如实暴露。
ENV TIKTOKEN_CACHE_DIR=/app/.tiktoken
RUN mkdir -p "$TIKTOKEN_CACHE_DIR" \
    && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')" \
    || echo "tiktoken 词表预热失败，运行期需可访问 openaipublic.blob.core.windows.net"

COPY adapter ./adapter
COPY app.py ./

EXPOSE 9621

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9621"]
