"""测试骨架：断言记录器 + 平台 REST 客户端（仅依赖 requests）。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import requests


class CheckFailed(AssertionError):
    """断言失败，携带可落盘证据。"""

    def __init__(self, message: str, evidence: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.evidence = evidence or {}


@dataclass
class Check:
    suite: str
    name: str
    status: str  # pass / fail / skip / error
    severity: str = "P1"
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "pass"


class Recorder:
    """按套件收集检查项；单条用例失败不阻断后续用例。"""

    def __init__(self) -> None:
        self.checks: list[Check] = []

    def run(self, suite: str, name: str, fn: Callable[[], Any], *, severity: str = "P1") -> Check:
        started = time.perf_counter()
        try:
            result = fn()
        except CheckFailed as exc:
            check = Check(suite, name, "fail", severity, str(exc), exc.evidence)
        except requests.RequestException as exc:
            check = Check(suite, name, "error", severity, f"网络异常：{type(exc).__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - 测试框架需要兜底，避免单例中断全量
            check = Check(suite, name, "error", severity, f"{type(exc).__name__}: {exc}")
        else:
            detail, evidence = "", {}
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
                detail, evidence = str(result[0]), result[1]
            elif result is not None:
                detail = str(result)
            check = Check(suite, name, "pass", severity, detail, evidence)
        check.ms = round((time.perf_counter() - started) * 1000, 1)
        self.checks.append(check)
        return check

    def skip(self, suite: str, name: str, reason: str, *, severity: str = "P2") -> Check:
        check = Check(suite, name, "skip", severity, reason)
        self.checks.append(check)
        return check

    def counts(self) -> dict[str, int]:
        out = {"pass": 0, "fail": 0, "skip": 0, "error": 0}
        for check in self.checks:
            out[check.status] = out.get(check.status, 0) + 1
        return out


@dataclass
class Response:
    status: int
    body: Any
    ms: float
    raw: str = ""

    @property
    def code(self) -> str:
        return str(self.body.get("code") or "") if isinstance(self.body, dict) else ""

    @property
    def message(self) -> str:
        return str(self.body.get("message") or "") if isinstance(self.body, dict) else ""

    def ok(self) -> bool:
        return 200 <= self.status < 300

    def brief(self, limit: int = 400) -> dict[str, Any]:
        body = self.raw if len(self.raw) > limit else self.body
        return {"status": self.status, "body": body}


class Api:
    """带 Cookie 会话的 REST 客户端；所有请求记录耗时。"""

    def __init__(self, base: str, *, timeout: float = 60.0) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.http = requests.Session()

    def login(self, username: str, password: str) -> Response:
        resp = self.post("/api/auth/login", {"username": username, "password": password})
        if not resp.ok():
            raise CheckFailed(f"登录失败 HTTP {resp.status} {resp.message}")
        return resp

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Response:
        started = time.perf_counter()
        raw = self.http.request(
            method,
            f"{self.base}{path}",
            json=json_body,
            timeout=timeout or self.timeout,
            **kwargs,
        )
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        text = raw.text
        try:
            body = raw.json()
        except ValueError:
            body = text
        return Response(raw.status_code, body, elapsed, text[:4000])

    # ---- 常用动词 ----
    def get(self, path: str, **kw: Any) -> Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: Any = None, **kw: Any) -> Response:
        return self.request("POST", path, json_body=body, **kw)

    def put(self, path: str, body: Any = None, **kw: Any) -> Response:
        return self.request("PUT", path, json_body=body, **kw)


def expect(cond: bool, message: str, **evidence: Any) -> None:
    if not cond:
        raise CheckFailed(message, evidence)


def expect_status(resp: Response, expected: int | tuple[int, ...], what: str) -> Response:
    codes = (expected,) if isinstance(expected, int) else expected
    expect(
        resp.status in codes,
        f"{what}：期望 HTTP {codes}，实际 {resp.status}（{resp.message or str(resp.body)[:200]}）",
        status=resp.status,
        body=resp.body if isinstance(resp.body, (dict, list)) else str(resp.body)[:400],
    )
    return resp


def dump(obj: Any, limit: int = 2000) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)[:limit]
    except (TypeError, ValueError):
        return str(obj)[:limit]
