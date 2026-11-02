"""OpenAI 兼容的本地假模型，用于在不消耗真实额度的情况下压测整条生成链路。

平台侧通过协议档环境变量指向本服务：`AI_PROFILE_<ID>_BASE_URL=http://<host>:<port>/v1`。
行为由 prompt 里的标记 `[[stub:<mode>]]` 决定（随来源文本一起进入模型上下文）：

| mode        | 模拟的上游异常/边界                    |
|-------------|----------------------------------------|
| normal      | 正常返回六策略用例 JSON                |
| fenced      | 用 ```json 围栏包裹（平台需兼容）      |
| malformed   | 返回非 JSON（平台应报 UPSTREAM）       |
| overquota   | 返回 2 倍条数（平台应裁剪到 max_count）|
| duplicate   | 全部重复（平台应去重）                 |
| missing     | 缺 expected/steps 字段                 |
| empty       | 返回空数组（平台应报错而非静默成功）   |
| upstream500 | 直接 500（平台应归一为 UPSTREAM）      |
| coverage    | 覆盖检查 JSON                          |
| fill        | 行级补全 JSON                          |
| chat        | 普通对话文本（AgentLoop 用）           |
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

STRATEGY_SEQ = ["正向"] * 4 + ["反向"] * 3 + ["边界"] * 2 + ["等价类"] + ["状态迁移"] + ["场景"]
PRIORITY_SEQ = ["HX", "HX", "FHX", "FHX", "BJ", "YC", "ZD", "BL"]


def _target_count(prompt: str) -> int:
    match = re.search(r"不超过\s*(\d+)\s*条", prompt)
    return int(match.group(1)) if match else 8


def _make_cases(n: int, *, omit: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index in range(n):
        case = {
            "strategy": STRATEGY_SEQ[index % len(STRATEGY_SEQ)],
            "priority": PRIORITY_SEQ[index % len(PRIORITY_SEQ)],
            "module": "登录",
            "submodule": "短信验证码",
            "feature_point": "验证码有效期",
            "name": f"验证码有效期场景 {index + 1}：输入正确验证码后登录",
            "precondition": "已获取未过期的验证码",
            # 每条用例的内容必须互不相同，否则会被平台的内容指纹去重，
            # 让「超配额裁剪」「缺字段」等场景测不出来。
            "steps": f"1. 打开登录页\n2. 输入手机号 1380000{index:04d} 与验证码\n3. 点击登录",
            "expected": f"登录成功并跳转首页，页面展示用户昵称（场景 {index + 1}）",
            "test_type": "核心业务",
        }
        for key in omit:
            case.pop(key, None)
        cases.append(case)
    return cases


def _reply_for(prompt: str, system: str) -> str:
    mode_match = re.search(r"\[\[stub:([a-z0-9_]+)\]\]", prompt)
    mode = mode_match.group(1) if mode_match else "normal"
    count = _target_count(prompt)

    if "你是测试评审专家" in system or mode == "coverage":
        return json.dumps(
            {
                "uncovered": [{"requirement": "并发领券超发", "reason": "候选里没有并发场景"}],
                "notes": "stub 覆盖检查",
            },
            ensure_ascii=False,
        )
    if mode == "fill":
        ids = re.findall(r'"id":\s*"([0-9a-zA-Z-]{6,})"', prompt)
        return json.dumps(
            [{"id": case_id, "expected": "返回 200 并展示结果", "precondition": "已登录"} for case_id in ids],
            ensure_ascii=False,
        )
    if mode == "malformed":
        return "抱歉，我无法按 JSON 输出。"
    if mode == "empty":
        return "[]"
    if mode == "missing":
        return json.dumps(_make_cases(min(count, 5), omit=("expected", "steps")), ensure_ascii=False)
    if mode == "duplicate":
        one = _make_cases(1)[0]
        return json.dumps([dict(one) for _ in range(min(count, 6))], ensure_ascii=False)
    if mode == "overquota":
        return json.dumps(_make_cases(count * 2), ensure_ascii=False)
    if mode == "neardupe":
        base = _make_cases(3)
        near = []
        for i in range(5):
            clone = dict(base[0])
            clone["name"] = f"验证码有效期校验 第{i + 1} 种写法"
            near.append(clone)
        return json.dumps(near, ensure_ascii=False)
    if mode == "noname":
        rows = _make_cases(5)
        for row in rows[2:]:
            row.pop("name", None)
        return json.dumps(rows, ensure_ascii=False)
    if mode == "fenced":
        return "```json\n" + json.dumps(_make_cases(count), ensure_ascii=False) + "\n```"
    if mode == "chat":
        return "我是测试用例设计专家。请提供需求文本或文件，我会生成待确认的用例草稿。"
    return json.dumps(_make_cases(count), ensure_ascii=False)


class _Handler(BaseHTTPRequestHandler):
    server_version = "AgentEvalStub/1.0"

    def log_message(self, *args: Any) -> None:  # noqa: D102 - 静默访问日志
        return

    # ---- helpers ----
    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, payload: dict[str, Any] | None = None) -> None:
        store = self.server.store  # type: ignore[attr-defined]
        if payload is not None:
            store["requests"].append(payload)

    # ---- routes ----
    def do_GET(self) -> None:  # noqa: N802
        store = self.server.store  # type: ignore[attr-defined]
        if self.path.startswith("/stub/requests"):
            self._json(200, {"requests": store["requests"]})
            return
        if self.path.rstrip("/") in {"/v1/models", "/models"}:
            self._json(200, {"data": [{"id": store["model"], "object": "model"}]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            body = {}
        if not self.path.endswith("/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return

        store = self.server.store  # type: ignore[attr-defined]
        messages = body.get("messages") or []
        prompt = "\n".join(str(m.get("content") or "") for m in messages if isinstance(m, dict))
        system = prompt
        mode_match = re.search(r"\[\[stub:([a-z0-9_]+)\]\]", prompt)
        mode = mode_match.group(1) if mode_match else "normal"
        self._record({
            "mode": mode,
            "model": body.get("model"),
            "temperature": body.get("temperature"),
            "max_tokens": body.get("max_tokens"),
            "stream": bool(body.get("stream")),
            "has_tools": bool(body.get("tools")),
            "prompt_chars": len(prompt),
            "system_head": (messages[0].get("content") or "")[:120] if messages else "",
            "ts": time.time(),
        })

        if mode == "upstream500":
            self._json(500, {"error": {"message": "stub upstream failure"}})
            return
        if mode == "slow":
            time.sleep(5)

        content = _reply_for(prompt, system if messages else "")
        if body.get("stream"):
            self._stream(content)
            return
        self._json(200, {
            "id": "stub-completion",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model") or store["model"],
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        })

    def _stream(self, content: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        chunk_size = 40
        for offset in range(0, len(content), chunk_size):
            chunk = {
                "id": "stub-completion",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "stub-model",
                "choices": [{"index": 0, "delta": {"content": content[offset:offset + chunk_size]},
                             "finish_reason": None}],
            }
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        done = {
            "id": "stub-completion", "object": "chat.completion.chunk",
            "created": int(time.time()), "model": "stub-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        }
        self.wfile.write(f"data: {json.dumps(done)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class StubModel:
    """线程内运行的假模型服务，支持上下文管理。"""

    def __init__(self, host: str = "0.0.0.0", port: int = 18080, model: str = "stub-model") -> None:
        self.httpd = ThreadingHTTPServer((host, port), _Handler)
        self.httpd.store = {"requests": [], "model": model}  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.host = host
        self.port = self.httpd.server_address[1]

    def start(self) -> StubModel:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def __enter__(self) -> StubModel:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    @property
    def requests_seen(self) -> list[dict[str, Any]]:
        return list(self.httpd.store["requests"])  # type: ignore[attr-defined]

    def reset(self) -> None:
        self.httpd.store["requests"] = []  # type: ignore[attr-defined]
