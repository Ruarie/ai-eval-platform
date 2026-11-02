"""套件：L0 环境契约、L1 生成链路（假模型）、L2 任务端到端。"""

from __future__ import annotations

import time
import uuid
from typing import Any

from .core import Api, Recorder, Response, expect, expect_status
from .stub_model import StubModel

SHORT_PRD = (
    "需求：手机号 + 短信验证码登录。验证码 6 位、5 分钟有效；"
    "连续错误 5 次锁定账号 30 分钟；未登录访问订单页跳转登录页。"
)


def _items(resp: Response) -> list[dict[str, Any]]:
    body = resp.body if isinstance(resp.body, dict) else {}
    items = body.get("items")
    expect(isinstance(items, list), "响应缺少 items 数组", body=resp.brief())
    return items


def _gen(api: Api, mode: str, **overrides: Any) -> Response:
    payload = {
        "source_text": f"{SHORT_PRD}\n[[stub:{mode}]]",
        "max_count": 6,
    }
    payload.update(overrides)
    return api.post("/api/case-sets/ai-generate", payload, timeout=120)


# ────────────────────────────── L0 ──────────────────────────────
def run_env(rec: Recorder, api: Api) -> None:
    def health() -> tuple[str, dict[str, Any]]:
        resp = expect_status(api.get("/api/health"), 200, "健康检查")
        body = resp.body if isinstance(resp.body, dict) else {}
        expect(body.get("status") == "ok", f"健康状态异常：{body.get('status')}", body=body)
        return f"version={body.get('version')} commit={body.get('commit')}", {"body": body}

    rec.run("env", "健康检查 /api/health", health, severity="P0")

    def unauthorized() -> tuple[str, dict[str, Any]]:
        fresh = Api(api.base)
        resp = fresh.get("/api/case-sets")
        expect_status(resp, 401, "未登录访问用例集")
        expect(resp.code == "UNAUTHORIZED", f"错误码不是 UNAUTHORIZED：{resp.code}")
        expect(bool(resp.message), "错误响应缺少 message")
        return "未登录被正确拒绝且错误体统一", resp.brief()

    rec.run("env", "未登录访问被拒绝", unauthorized, severity="P0")

    def bad_login() -> tuple[str, dict[str, Any]]:
        fresh = Api(api.base)
        resp = fresh.post("/api/auth/login", {"username": "admin", "password": "definitely-wrong"})
        expect_status(resp, 401, "错误密码登录")
        expect(resp.code == "UNAUTHORIZED", f"错误码异常：{resp.code}")
        return "错误密码返回 401/UNAUTHORIZED", resp.brief()

    rec.run("env", "错误密码登录拒绝", bad_login)

    def unknown_path() -> tuple[str, dict[str, Any]]:
        resp = api.get("/api/definitely-not-exists")
        expect_status(resp, 404, "未知路径")
        unified = isinstance(resp.body, dict) and "code" in resp.body and "message" in resp.body
        expect(unified, "未知路径未返回统一错误体 {code,message}", body=resp.brief())
        return "统一错误体", resp.brief()

    rec.run("env", "未知路径错误体统一", unknown_path, severity="P2")

    def agent_ui() -> tuple[str, dict[str, Any]]:
        resp = expect_status(api.get("/api/sessions/agent-ui"), 200, "Agent UI 能力")
        body = resp.body if isinstance(resp.body, dict) else {}
        agents = {item.get("id") for item in body.get("agents") or []}
        expect("testcase-agent" in agents, f"缺少 testcase-agent 专家：{agents}", body=body)
        return (
            f"专家 {len(agents)} 个，协议档 {len(body.get('profiles') or [])} 个，"
            f"unavailable_reason={body.get('unavailable_reason')!r}",
            {"unavailable_reason": body.get("unavailable_reason"), "profile": body.get("profile")},
        )

    rec.run("env", "Agent 能力与专家注册", agent_ui)

    def profile_ready() -> tuple[str, dict[str, Any]]:
        body = api.get("/api/sessions/agent-ui").body or {}
        reason = body.get("unavailable_reason")
        expect(not reason, f"Agent 协议档不可用：{reason}", unavailable_reason=reason)
        return "Agent 协议档可用", {}

    rec.run("env", "Agent 协议档可用性", profile_ready, severity="P1")


# ────────────────────────────── L1 ──────────────────────────────
def run_generation(rec: Recorder, api: Api, stub: StubModel) -> None:
    def normal() -> tuple[str, dict[str, Any]]:
        stub.reset()
        resp = _gen(api, "normal")
        expect_status(resp, 200, "正常生成")
        items = _items(resp)
        expect(len(items) > 0, "模型返回了空用例集")
        body = resp.body if isinstance(resp.body, dict) else {}
        expect("checks" in body, "响应缺少自检 checks")
        expect("dropped" in body, "响应缺少裁剪统计 dropped")
        required = ("strategy", "priority", "module", "feature_point", "name", "steps", "expected")
        missing = {key for item in items for key in required if not str(item.get(key) or "").strip()}
        expect(not missing, f"候选用例字段缺失：{sorted(missing)}")
        return f"{len(items)} 条候选，checks={len(body.get('checks') or [])}", body

    rec.run("gen", "候选用例正常生成", normal, severity="P0")

    def prompt_contract() -> tuple[str, dict[str, Any]]:
        seen = stub.requests_seen
        expect(bool(seen), "假模型没有收到任何请求", seen=seen)
        last = seen[-1]
        expect(last.get("temperature") == 0.3, f"生成温度不是 0.3：{last.get('temperature')}", last=last)
        expect(last.get("max_tokens") == 8192, f"token 预算异常：{last.get('max_tokens')}", last=last)
        expect(
            "正向" in last.get("system_head", "") or last.get("prompt_chars", 0) > 500,
            "system prompt 疑似未注入策略约束",
            last=last,
        )
        return f"temperature={last.get('temperature')} max_tokens={last.get('max_tokens')}", last

    rec.run("gen", "生成请求参数与 prompt 注入", prompt_contract)

    def fenced() -> tuple[str, dict[str, Any]]:
        resp = _gen(api, "fenced")
        expect_status(resp, 200, "围栏 JSON 容错")
        return f"{len(_items(resp))} 条", {}

    rec.run("gen", "代码围栏 JSON 容错", fenced)

    def malformed() -> tuple[str, dict[str, Any]]:
        resp = _gen(api, "malformed")
        expect_status(resp, 502, "非 JSON 输出")
        expect(resp.code == "UPSTREAM", f"错误码应为 UPSTREAM，实际 {resp.code}", body=resp.brief())
        return "归一为 UPSTREAM，未崩溃", resp.brief()

    rec.run("gen", "模型输出非 JSON 的错误归一", malformed, severity="P0")

    def empty() -> tuple[str, dict[str, Any]]:
        resp = _gen(api, "empty")
        expect_status(resp, 502, "空数组输出")
        expect(resp.code == "UPSTREAM", f"错误码应为 UPSTREAM，实际 {resp.code}", body=resp.brief())
        return "空结果未静默成功", resp.brief()

    rec.run("gen", "模型返回空数组不允许静默成功", empty, severity="P0")

    def overquota() -> tuple[str, dict[str, Any]]:
        resp = _gen(api, "overquota", max_count=4)
        expect_status(resp, 200, "超配额输出")
        items = _items(resp)
        expect(len(items) <= 4, f"未裁剪到 max_count=4，实际 {len(items)} 条", count=len(items))
        body = resp.body if isinstance(resp.body, dict) else {}
        dropped = body.get("dropped") or {}
        expect(
            int(dropped.get("dropped_over_quota", 0)) > 0,
            f"裁剪统计未记录 over_quota：{dropped}",
            dropped=dropped,
        )
        return f"裁剪后 {len(items)} 条，dropped={dropped}", dropped

    rec.run("gen", "超出条数上限被裁剪", overquota, severity="P0")

    def duplicate() -> tuple[str, dict[str, Any]]:
        resp = _gen(api, "duplicate", max_count=6)
        expect_status(resp, 200, "重复输出")
        items = _items(resp)
        body = resp.body if isinstance(resp.body, dict) else {}
        dropped = body.get("dropped") or {}
        expect(len(items) < 6, f"重复用例未被去重，仍返回 {len(items)} 条", count=len(items))
        expect(
            int(dropped.get("dropped_duplicate", 0)) > 0,
            f"去重统计未记录：{dropped}",
            dropped=dropped,
        )
        return f"去重后 {len(items)} 条", dropped

    rec.run("gen", "完全重复用例被去重", duplicate)

    def near_duplicate() -> tuple[str, dict[str, Any]]:
        # 全部压到正向策略，避免配额裁剪掩盖「近似重复未被识别」的问题。
        resp = _gen(
            api, "neardupe", max_count=6,
            strategy_weights={"positive": 100, "negative": 0, "boundary": 0,
                              "equivalence": 0, "state": 0, "scenario": 0},
        )
        expect_status(resp, 200, "近似重复输出")
        items = _items(resp)
        expect(
            len(items) <= 2,
            f"近似重复（同步骤同预期、仅名称不同）未被合并，保留 {len(items)} 条",
            count=len(items),
            sample=[item.get("name") for item in items[:5]],
        )
        return f"保留 {len(items)} 条", {}

    rec.run("gen", "近似重复用例应被识别", near_duplicate, severity="P2")

    def missing_fields() -> tuple[str, dict[str, Any]]:
        resp = _gen(api, "missing")
        expect_status(resp, (200, 422, 400), "字段缺失输出")
        if resp.status != 200:
            return "缺字段输出被拒绝", resp.brief()
        items = _items(resp)
        incomplete = [
            item for item in items
            if not str(item.get("expected") or "").strip() or not str(item.get("steps") or "").strip()
        ]
        unflagged = [item for item in incomplete if not item.get("pending_complete")]
        expect(
            not unflagged,
            f"{len(unflagged)} 条缺 expected/steps 的候选没有 pending_complete 标记，"
            "脚本/导入类消费方无法识别待补全",
            sample=unflagged[:2],
        )
        return f"{len(incomplete)} 条缺字段候选已标记待补全", {"pending": len(incomplete)}

    rec.run("gen", "缺关键字段的候选应被拦截或标记", missing_fields, severity="P2")

    def noname() -> tuple[str, dict[str, Any]]:
        resp = _gen(api, "noname", max_count=6)
        expect_status(resp, (200, 502), "缺名称输出")
        body = resp.body if isinstance(resp.body, dict) else {}
        items = body.get("items") or []
        dropped = body.get("dropped") or {}
        if resp.status == 200 and len(items) < 5:
            lost = 5 - len(items)
            recorded = sum(int(v) for v in dropped.values() if isinstance(v, int))
            expect(
                recorded >= lost,
                f"{lost} 条因缺名称被静默丢弃，dropped 统计只记录 {recorded} 条",
                dropped=dropped,
                returned=len(items),
            )
        return f"返回 {len(items)} 条，dropped={dropped}", dropped

    rec.run("gen", "缺名称条目不得静默丢弃", noname, severity="P2")

    def invalid_params() -> tuple[str, dict[str, Any]]:
        cases = []
        resp = api.post("/api/case-sets/ai-generate", {"source_text": SHORT_PRD, "strategy_weights": {"positive": 90}})
        cases.append(("权重合计≠100", resp, (400, 422)))
        resp = api.post("/api/case-sets/ai-generate", {"source_text": SHORT_PRD, "max_count": 0})
        cases.append(("max_count=0", resp, (400, 422)))
        resp = api.post("/api/case-sets/ai-generate", {"source_text": SHORT_PRD, "max_count": 81})
        cases.append(("max_count=81", resp, (400, 422)))
        resp = api.post("/api/case-sets/ai-generate", {"source_text": "   "})
        cases.append(("空白需求", resp, (400, 422)))
        detail = {}
        for what, response, want in cases:
            expect_status(response, want, what)
            detail[what] = response.status
        return "参数校验全部生效", detail

    rec.run("gen", "非法参数校验", invalid_params)

    def coverage() -> tuple[str, dict[str, Any]]:
        resp = api.post(
            "/api/case-sets/ai-coverage",
            {
                "source_text": f"{SHORT_PRD}\n[[stub:coverage]]",
                "cases": [{"name": "验证码有效期校验", "strategy": "边界", "module": "登录"}],
            },
            timeout=120,
        )
        expect_status(resp, 200, "覆盖检查")
        body = resp.body if isinstance(resp.body, dict) else {}
        expect(isinstance(body.get("uncovered"), list), "覆盖检查缺少 uncovered 数组", body=body)
        return f"uncovered={len(body.get('uncovered') or [])}", body

    rec.run("gen", "需求覆盖检查", coverage)

    def ai_fill() -> tuple[str, dict[str, Any]]:
        created = api.post("/api/case-sets", {"name": f"agent-eval-fill-{uuid.uuid4().hex[:6]}"})
        expect_status(created, 201, "创建空用例集")
        set_id = created.body["id"]
        revision = created.body.get("revision", 1)
        saved = api.put(
            f"/api/case-sets/{set_id}/cases",
            {
                "cases": [{"strategy": "正向", "priority": "HX", "module": "登录",
                           "name": "验证码正确时登录成功", "steps": "1. 输入验证码\n2. 点击登录"}],
                "expected_revision": revision,
            },
        )
        expect_status(saved, 200, "保存用例")
        case_id = (saved.body.get("items") or [{}])[0].get("id")
        expect(bool(case_id), "保存后未返回用例 id", body=saved.brief())
        resp = api.post(
            f"/api/case-sets/{set_id}/ai-fill",
            {"case_ids": [case_id], "instruction": "补充预期结果 [[stub:fill]]"},
            timeout=120,
        )
        expect_status(resp, 200, "行级补全")
        return "行级补全返回候选", {"status": resp.status}
        # 清理：无用例落库，直接废弃
    rec.run("gen", "行级 AI 补全", ai_fill)


# ────────────────────────────── L1 用例集生命周期 ──────────────────────────────
def _new_case_set(api: Api, prefix: str = "agent-eval") -> dict[str, Any]:
    resp = api.post("/api/case-sets", {"name": f"{prefix}-{uuid.uuid4().hex[:6]}"})
    expect_status(resp, 201, "创建用例集")
    return resp.body if isinstance(resp.body, dict) else {}


def run_lifecycle(rec: Recorder, api: Api) -> None:
    state: dict[str, Any] = {}

    def from_candidates() -> tuple[str, dict[str, Any]]:
        resp = api.post(
            "/api/case-sets/from-candidates",
            {
                "name": f"agent-eval-cand-{uuid.uuid4().hex[:6]}",
                "cases": [
                    {"strategy": "正向", "priority": "HX", "module": "登录",
                     "name": f"候选保存校验 {uuid.uuid4().hex[:4]}", "steps": "1. 步骤",
                     "expected": "返回成功", "feature_point": "登录"},
                ],
            },
        )
        expect_status(resp, 201, "候选入库")
        body = resp.body if isinstance(resp.body, dict) else {}
        expect(body.get("status") == "generated", f"新建用例集状态应为 generated：{body.get('status')}")
        expect(body.get("generated_count") == 1, f"generated_count 异常：{body.get('generated_count')}")
        state["set_id"] = body.get("id")
        state["revision"] = body.get("revision", 1)
        return f"set={state['set_id']} revision={state['revision']}", {"body_keys": list(body)}

    rec.run("case", "候选一次性入库", from_candidates, severity="P0")

    def revision_conflict() -> tuple[str, dict[str, Any]]:
        set_id = state.get("set_id")
        expect(bool(set_id), "前置用例集创建失败，无法测试并发冲突")
        resp = api.put(
            f"/api/case-sets/{set_id}/cases",
            {"cases": [{"strategy": "正向", "priority": "HX", "module": "登录", "name": "冲突写入"}],
             "expected_revision": 999},
        )
        expect_status(resp, 409, "过期 revision 保存")
        expect(resp.code == "CONCURRENCY", f"错误码应为 CONCURRENCY，实际 {resp.code}")
        return "过期 revision 被拒绝", resp.brief()

    rec.run("case", "并发保存版本冲突", revision_conflict, severity="P0")

    def save_and_refresh() -> tuple[str, dict[str, Any]]:
        set_id = state["set_id"]
        resp = api.put(
            f"/api/case-sets/{set_id}/cases",
            {
                "cases": [
                    {"strategy": "正向", "priority": "HX", "module": "登录", "name": "登录成功跳转首页",
                     "steps": "1. 输入验证码\n2. 点击登录", "expected": "跳转首页", "feature_point": "登录成功"},
                    {"strategy": "反向", "priority": "YC", "module": "登录", "name": "验证码错误提示剩余次数",
                     "steps": "1. 输入错误验证码\n2. 提交", "expected": "提示还可尝试 N 次", "feature_point": "错误次数"},
                ],
                "expected_revision": state["revision"],
            },
        )
        expect_status(resp, 200, "保存用例行")
        body = resp.body if isinstance(resp.body, dict) else {}
        state["revision"] = body.get("revision", state["revision"] + 1)
        expect(len(body.get("items") or []) == 2, f"保存后条数异常：{len(body.get('items') or [])}")
        return f"revision→{state['revision']}", {"checks": body.get("checks")}

    rec.run("case", "用例行批量保存并重算自检", save_and_refresh, severity="P0")

    def confirm() -> tuple[str, dict[str, Any]]:
        set_id = state["set_id"]
        resp = api.post(f"/api/case-sets/{set_id}/confirm", {"ok": True, "expected_revision": state["revision"]})
        expect_status(resp, 200, "确认入库")
        body = resp.body if isinstance(resp.body, dict) else {}
        expect(body.get("status") == "confirmed", f"状态应为 confirmed：{body.get('status')}")
        expect(body.get("confirmed_count") == body.get("generated_count"), "confirmed_count 与 generated_count 不一致")
        return f"confirmed_count={body.get('confirmed_count')}", {}

    rec.run("case", "确认入库与计数", confirm, severity="P0")

    def immutable_after_confirm() -> tuple[str, dict[str, Any]]:
        set_id = state["set_id"]
        resp = api.put(
            f"/api/case-sets/{set_id}/cases",
            {"cases": [{"strategy": "正向", "priority": "HX", "module": "x", "name": "确认后再改"}],
             "expected_revision": state["revision"]},
        )
        expect(
            resp.status in (400, 403, 409),
            f"已确认用例集仍可写入，HTTP {resp.status}",
            body=resp.brief(),
        )
        return f"写入被拒绝 HTTP {resp.status}/{resp.code}", resp.brief()

    rec.run("case", "已确认用例集不可改", immutable_after_confirm, severity="P0")

    def empty_confirm() -> tuple[str, dict[str, Any]]:
        empty = _new_case_set(api, "agent-eval-empty")
        resp = api.post(
            f"/api/case-sets/{empty['id']}/confirm",
            {"ok": True, "expected_revision": empty.get("revision", 0)},
        )
        expect_status(resp, 400, "空用例集确认")
        return "空用例集拒绝确认", resp.brief()

    rec.run("case", "空用例集不可确认", empty_confirm)

    def cancel() -> tuple[str, dict[str, Any]]:
        target = _new_case_set(api, "agent-eval-cancel")
        resp = api.post(
            f"/api/case-sets/{target['id']}/cancel",
            {"expected_revision": target.get("revision", 0), "reason": "agent-eval"},
        )
        expect_status(resp, 200, "废弃用例集")
        body = resp.body if isinstance(resp.body, dict) else {}
        expect(body.get("status") == "cancelled", f"状态应为 cancelled：{body.get('status')}")
        return "cancelled", {}

    rec.run("case", "废弃用例集", cancel)


# ────────────────────────────── L2 任务端到端 ──────────────────────────────
def run_task_e2e(rec: Recorder, api: Api, *, timeout_s: float = 180.0) -> None:
    state: dict[str, Any] = {}

    def enqueue() -> tuple[str, dict[str, Any]]:
        resp = api.post(
            "/api/tasks",
            {
                "kind": "testcase",
                "case_source": {"text": f"{SHORT_PRD}\n[[stub:normal]]"},
                "max_count": 5,
            },
        )
        expect_status(resp, 201, "创建用例生成任务")
        body = resp.body if isinstance(resp.body, dict) else {}
        expect(body.get("status") in {"queued", "running"}, f"初始状态异常：{body.get('status')}")
        state["task_id"] = body.get("id")
        return f"task={state['task_id']} status={body.get('status')}", {}

    rec.run("task", "创建用例生成任务入队", enqueue, severity="P0")

    def wait_finish() -> tuple[str, dict[str, Any]]:
        task_id = state.get("task_id")
        expect(bool(task_id), "任务未创建，无法等待")
        deadline = time.time() + timeout_s
        last: dict[str, Any] = {}
        while time.time() < deadline:
            resp = api.get(f"/api/tasks/{task_id}")
            if resp.ok() and isinstance(resp.body, dict):
                last = resp.body
                if last.get("status") in {"awaiting_case_confirm", "succeeded", "failed", "cancelled"}:
                    break
            time.sleep(2)
        status = last.get("status")
        expect(
            status == "awaiting_case_confirm",
            f"任务未进入 awaiting_case_confirm，最终状态 {status}，result={last.get('result')}",
            task=last,
        )
        result = last.get("result") or {}
        state["set_id"] = result.get("case_set_id") or result.get("set_id")
        return f"status={status}", {"result": result}

    rec.run("task", "Worker 执行并生成待确认草稿", wait_finish, severity="P0")

    def draft_ready() -> tuple[str, dict[str, Any]]:
        set_id = state.get("set_id")
        expect(bool(set_id), "任务结果未回填 case_set_id", task=state)
        resp = api.get(f"/api/case-sets/{set_id}")
        expect_status(resp, 200, "读取任务生成的用例集")
        body = resp.body if isinstance(resp.body, dict) else {}
        expect(body.get("status") == "generated", f"用例集状态应为 generated：{body.get('status')}")
        expect(int(body.get("generated_count") or 0) > 0, "草稿没有被写入用例行", body=body)
        state["revision"] = body.get("revision", 1)
        expect(bool(body.get("expires_at")), "草稿缺少 expires_at（72h 确认窗口）", body=body)
        return f"draft {body.get('generated_count')} 条，expires_at={body.get('expires_at')}", {}

    rec.run("task", "草稿落库含确认窗口", draft_ready, severity="P0")

    def confirm_and_task() -> tuple[str, dict[str, Any]]:
        set_id, task_id = state.get("set_id"), state.get("task_id")
        resp = api.post(f"/api/case-sets/{set_id}/confirm", {"ok": True, "expected_revision": state.get("revision", 1)})
        expect_status(resp, 200, "确认草稿")
        task = api.get(f"/api/tasks/{task_id}")
        body = task.body if isinstance(task.body, dict) else {}
        expect(body.get("status") == "succeeded", f"确认后任务状态应为 succeeded：{body.get('status')}")
        return "确认后任务 succeeded", {}

    rec.run("task", "确认草稿联动任务成功", confirm_and_task, severity="P0")

    def out_of_scope() -> tuple[str, dict[str, Any]]:
        resp = api.post("/api/tasks", {"kind": "benchmark", "profile_ids": [], "dataset_id": "x"})
        expect(
            resp.status in (400, 404, 422),
            f"已下线的 benchmark 任务仍可创建，HTTP {resp.status}",
            body=resp.brief(),
        )
        return f"拒绝创建 benchmark（HTTP {resp.status}/{resp.code}）", resp.brief()

    rec.run("task", "已下线任务类型不可创建", out_of_scope)
