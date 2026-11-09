"""Embedding 客户端回归：端点拼接、载荷形状与失败归一（不访问真实供应商）。"""

import httpx
import pytest

from app.errors import AppError, ErrorCode
from app.llm import embeddings


class _FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """替换 httpx.Client，记录请求并返回预制响应或异常。"""

    calls: list[dict] = []
    response: _FakeResponse | None = None
    error: Exception | None = None

    def __init__(self, **_kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def post(self, url, json=None, headers=None, **_kwargs):
        type(self).calls.append({"url": url, "json": json, "headers": headers})
        if type(self).error is not None:
            raise type(self).error
        return type(self).response


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch):
    _FakeClient.calls = []
    _FakeClient.response = None
    _FakeClient.error = None
    monkeypatch.setattr(embeddings.httpx, "Client", _FakeClient)
    monkeypatch.setattr(
        embeddings, "resolve_config", lambda: ("http://embed.local/v1", "bge-m3", "secret-key")
    )
    return _FakeClient


def test_embed_texts_builds_endpoint_and_payload(fake_client) -> None:
    """端点自动补 /embeddings，批量输入原样提交并返回同序向量。"""
    fake_client.response = _FakeResponse(
        200, {"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
    )
    vectors = embeddings.embed_texts(["第一段", "second"], timeout_s=1.5)
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    call = fake_client.calls[0]
    assert call["url"] == "http://embed.local/v1/embeddings"
    assert call["json"] == {"model": "bge-m3", "input": ["第一段", "second"]}
    assert call["headers"]["Authorization"] == "Bearer secret-key"


def test_embed_texts_keeps_full_endpoint(fake_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """已带 /embeddings 的完整端点不重复拼接，无密钥时不带鉴权头。"""
    monkeypatch.setattr(
        embeddings, "resolve_config", lambda: ("http://embed.local/v1/embeddings", "bge-m3", "")
    )
    fake_client.response = _FakeResponse(200, {"data": [{"embedding": [1.0]}]})
    embeddings.embed_texts(["x"])
    assert fake_client.calls[0]["url"] == "http://embed.local/v1/embeddings"
    assert "Authorization" not in fake_client.calls[0]["headers"]


def test_embed_texts_rejects_incomplete_config(fake_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置端点或模型时 fail-closed，不发出请求。"""
    monkeypatch.setattr(embeddings, "resolve_config", lambda: ("", "bge-m3", ""))
    with pytest.raises(AppError) as error:
        embeddings.embed_texts(["x"])
    assert error.value.code == ErrorCode.VALIDATION
    assert fake_client.calls == []


def test_embed_texts_normalizes_upstream_errors(fake_client) -> None:
    """上游错误只暴露状态码，不回显响应正文。"""
    fake_client.response = _FakeResponse(500, {"error": "internal secret detail"})
    with pytest.raises(AppError) as error:
        embeddings.embed_texts(["x"])
    assert error.value.code == ErrorCode.VALIDATION
    assert "500" in error.value.message
    assert "secret detail" not in error.value.message


def test_embed_texts_rejects_shape_mismatch(fake_client) -> None:
    """条数或维度不一致视为上游异常，不做部分成功。"""
    fake_client.response = _FakeResponse(200, {"data": [{"embedding": [0.1]}]})
    with pytest.raises(AppError) as error:
        embeddings.embed_texts(["a", "b"])
    assert error.value.code == ErrorCode.VALIDATION

    fake_client.response = _FakeResponse(
        200, {"data": [{"embedding": [0.1]}, {"embedding": [0.2, 0.3]}]}
    )
    with pytest.raises(AppError) as error:
        embeddings.embed_texts(["a", "b"])
    assert error.value.code == ErrorCode.VALIDATION


def test_embed_texts_normalizes_timeout(fake_client) -> None:
    """超时归一为 VALIDATION，供调用方降级为关键词召回。"""
    fake_client.error = httpx.TimeoutException("boom")
    with pytest.raises(AppError) as error:
        embeddings.embed_texts(["x"])
    assert error.value.code == ErrorCode.VALIDATION
    assert "超时" in error.value.message
