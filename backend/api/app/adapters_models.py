"""上游模型列表探测与 Base URL 归一化（从 adapters 拆出）。

只负责「向协议端点问可用模型」这一件事，与具体协议调用（chat/completions、
messages、responses）解耦；协议适配层复用 service_base_url 生成真实端点。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .errors import AppError, ErrorCode


def service_base_url(base_url: str) -> str:
    """规范化协议服务根地址，智能剥离常见后缀（如 /v1/models、/models、/chat/completions、/messages 等）。

    三种协议的具体端点由本适配器统一追加相应路径段。协议档常见的
    OpenAI 兼容地址通常带 /v1，因此这里会智能剥离末尾的子路径与版本段，
    避免真实请求错误落到 /models/v1/models、/v1/v1/... 等错误地址；不修改数据库中用户保存的原值。
    """
    base = base_url.strip().rstrip("/")
    for suffix in (
        "/chat/completions",
        "/responses",
        "/messages",
        "/models",
        "/v1/models",
        "/v1/chat/completions",
        "/v1/messages",
        "/api/tags",
        "/api/v1/models",
    ):
        if base.endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
            break
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base

def _anthropic_model_list_roots(base_url: str) -> list[str]:
    """为挂在子路径上的 Anthropic 兼容网关推导宿主根模型列表候选地址。

    DeepSeek（``…/anthropic``）、Kimi、智谱等官方把 Anthropic 协议发布在
    前缀子路径下，``/v1/models`` 模型列表仍位于宿主根或上一级路径；这里只
    生成候选 URL 供逐个尝试，不修改协议档中保存的原值。
    """
    parsed = urlsplit(base_url)
    segments = [seg for seg in parsed.path.split("/") if seg]
    if not segments:
        return []
    origin = f"{parsed.scheme}://{parsed.netloc}"
    roots: list[str] = []
    # 先去掉最后一段得到上一级路径，再回退到宿主根；重复候选由调用方去重。
    for depth in (len(segments) - 1, 0):
        prefix = "/" + "/".join(segments[:depth]) if depth else ""
        candidate = f"{origin}{prefix}"
        if candidate != base_url and candidate not in roots:
            roots.append(candidate)
    return roots

def _remote_model_parameters(item: Mapping[str, object]) -> list[dict[str, object]]:
    """保留上游模型目录声明的可选请求字段，供前端构造模型规格。"""
    raw_parameters = item.get("parameters")
    if not isinstance(raw_parameters, list):
        return []
    parameters: list[dict[str, object]] = []
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, Mapping):
            continue
        parameter_id = str(raw_parameter.get("id") or "").strip()
        raw_values = raw_parameter.get("values")
        if not parameter_id or not isinstance(raw_values, list):
            continue
        values = [str(value) for value in raw_values if isinstance(value, str | int | float | bool)]
        if values:
            parameters.append({"id": parameter_id, "values": values})
    return parameters

def fetch_remote_models(
    *,
    protocol: str,
    base_url: str,
    api_key: str | None = None,
    anthropic_version: str | None = None,
    timeout_s: float = 15.0,
) -> list[dict]:
    """从目标服务端点动态获取可用模型列表（如 /v1/models）。

    统一返回结构：``[{"id": "模型标识", "name": "显示名称", "owned_by": "所属供应商/系统"}]``。
    真实调用远程端点解析实际可用模型，不返回硬编码假数据。
    """
    base = service_base_url(base_url)
    raw_clean = base_url.strip().rstrip("/")

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ai-eval-platform/1.0",
    }
    if api_key:
        if protocol == "anthropic_messages":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = anthropic_version or "2023-06-01"
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    candidate_urls: list[str] = []
    if protocol == "anthropic_messages":
        candidate_urls = [
            f"{base}/v1/models",
            f"{base}/models",
            f"{base}/api/v1/models",
        ]
        if raw_clean not in candidate_urls:
            candidate_urls.append(raw_clean)
            if not raw_clean.endswith("/models"):
                candidate_urls.append(f"{raw_clean}/models")
        # DeepSeek /anthropic 这类子路径网关通常不在子路径下发布模型列表，
        # 追加宿主根/上一级路径的候选（api.deepseek.com/v1/models 等）。
        for root in _anthropic_model_list_roots(base):
            for path in ("/v1/models", "/models"):
                if f"{root}{path}" not in candidate_urls:
                    candidate_urls.append(f"{root}{path}")
    else:
        candidate_urls = [
            f"{base}/v1/models",
            f"{base}/models",
            f"{base}/api/tags",
            f"{base}/api/v1/models",
        ]
        if raw_clean not in candidate_urls:
            candidate_urls.append(raw_clean)
            if not raw_clean.endswith("/models"):
                candidate_urls.append(f"{raw_clean}/models")

    urls_to_try: list[str] = []
    for u in candidate_urls:
        if u not in urls_to_try and (u.startswith("http://") or u.startswith("https://")):
            urls_to_try.append(u)

    last_error: Exception | None = None
    data: dict | list | None = None
    for url in urls_to_try:
        try:
            req = Request(url, headers=headers, method="GET")
            with urlopen(req, timeout=timeout_s) as response:
                raw_bytes = response.read()
                data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
                if isinstance(data, dict | list):
                    break
        except HTTPError as exc:
            last_error = exc
            if exc.code in (401, 403):
                raise AppError(ErrorCode.UNAUTHORIZED, f"上游鉴权失败 ({exc.code})，请检查 API Key 凭据") from exc
            continue
        except TimeoutError as exc:
            last_error = exc
            continue
        except URLError as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            continue

    models_list: list[dict] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and (item.get("id") or item.get("name") or item.get("display_name")):
                m_id = str(item.get("id") or item.get("name") or item.get("display_name"))
                model_item: dict[str, object] = {
                    "id": m_id,
                    "name": str(item.get("display_name") or item.get("name") or m_id),
                    "owned_by": str(item.get("owned_by") or item.get("root") or ("anthropic" if protocol == "anthropic_messages" else "remote")),
                }
                parameters = _remote_model_parameters(item)
                if parameters:
                    model_item["parameters"] = parameters
                models_list.append(model_item)
    elif isinstance(data, dict):
        raw_items = data.get("data") or data.get("models") or data.get("items") or []
        if isinstance(raw_items, dict) and isinstance(raw_items.get("models"), list):
            raw_items = raw_items["models"]
        if isinstance(raw_items, list):
            for item in raw_items:
                if isinstance(item, dict) and (item.get("id") or item.get("name") or item.get("display_name")):
                    m_id = str(item.get("id") or item.get("name") or item.get("display_name"))
                    model_item = {
                        "id": m_id,
                        "name": str(item.get("display_name") or item.get("name") or m_id),
                        "owned_by": str(item.get("owned_by") or item.get("root") or ("anthropic" if protocol == "anthropic_messages" else ("ollama" if "models" in data else "remote"))),
                    }
                    parameters = _remote_model_parameters(item)
                    if parameters:
                        model_item["parameters"] = parameters
                    models_list.append(model_item)

    if models_list:
        # 去重并排序
        seen_ids: set[str] = set()
        deduped: list[dict] = []
        for m in models_list:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                deduped.append(m)
        deduped.sort(key=lambda x: x["id"].lower())
        return deduped

    if last_error:
        if isinstance(last_error, HTTPError):
            if last_error.code in (401, 403):
                raise AppError(ErrorCode.UNAUTHORIZED, f"上游鉴权失败 ({last_error.code})，请检查 API Key 凭据") from last_error
            if last_error.code == 404:
                raise AppError(
                    ErrorCode.NOT_FOUND,
                    "目标服务端点未开放模型列表接口 (HTTP 404)。请检查 Base URL 地址或直接在输入框手动填入模型标识名（如 claude-3-7-sonnet-20250219、gpt-4o 等）",
                ) from last_error
            raise AppError(ErrorCode.UPSTREAM, f"上游服务返回 HTTP {last_error.code}，无法获取模型列表") from last_error
        if isinstance(last_error, TimeoutError):
            raise AppError(ErrorCode.TIMEOUT, "获取模型列表超时，请检查服务端点网络") from last_error
        if isinstance(last_error, URLError):
            raise AppError(ErrorCode.UPSTREAM, f"连接上游端点失败: {getattr(last_error, 'reason', last_error)}") from last_error
        raise AppError(ErrorCode.UPSTREAM, f"无法从端点获取模型列表: {last_error}") from last_error
    raise AppError(ErrorCode.UPSTREAM, "端点未返回可解析的模型列表，请检查端点地址或手动输入模型标识名")
