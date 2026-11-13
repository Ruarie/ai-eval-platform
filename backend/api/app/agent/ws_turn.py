"""回合执行：模型调用、工具审批注入、落库与取消收尾。

所有 ws 模块级依赖（会话/广播/注册表/模型配置）统一经 ``ws_router.X`` 访问，
保证既有测试对 ``ws.<name>`` 的打桩继续生效。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger("ai-eval.ws")


async def run_turn(
    session_id: str,
    websocket: Any,
    state: Any,
    abort: asyncio.Event,
    *,
    user_id: str,
    turn_id: str | None = None,
    workflow_confirm: dict | None = None,
    turn_sink: dict | None = None,
    resume: object | None = None,
    resume_thread_id: str | None = None,
) -> None:
    from ..routers import ws as ws_router

    """后台执行一轮 LangGraph Agent，并把图输出统一投影为 WS 事件。

    图节点只返回纯数据（custom 瞬态帧 + pending_events 事件意图）；本函数
    消费 ``astream`` 输出后统一 emit（§2.5 事件桥接）。``should_abort`` 与
    api_key 经 ``RunnableConfig.configurable`` 注入（O-12 迁移），不入 State。

    ``workflow_confirm`` 为确认卡回执重放（H2 批次 2）：非空时注入
    ``configurable``，Workflow W5 合并槽位后放行 W6 入队、W7 收尾——入队仍
    唯一经 W6（不在此处直接入队）。

    ``resume`` / ``resume_thread_id`` 为 H5 HITL 审批恢复：以原中断回合的
    thread_id 从检查点 ``Command(resume=...)`` 恢复执行（恢复前清空图内
    pending_events，避免事件重放；resume 至多一次由审批卡行锁清卡保证）。
    """
    if turn_id:
        with ws_router._TURN_LOCK:
            current = ws_router._SESSION_TURNS.get(session_id)
            if current is not None and current.turn_id == turn_id:
                current.started = True
    db = ws_router.SessionLocal()
    # Router 审计三元组（H1）：先置空再进 try，任何阶段异常收尾均可安全携带
    router_audit: dict | None = None
    try:
        config, profile = ws_router._selected_model_config(db)
        # 沙箱根先行解析（F3/G5 + BLK-1/BLK-2 修复）：session_row 提前查询，
        # 绑定会话经带行态校验的 ws_router.resolve_session_sandbox_db 统一解析——附件
        # staging（_window_messages）与工具注入共用同一根；解析失败/绑定失效
        # → 空串（工具 fail-closed，附件回退内联注入），不阻断回合。
        session_row = db.query(ws_router.AgentSession).filter(ws_router.AgentSession.id == session_id).first()
        sandbox_dir = ""
        try:
            if session_row is not None:
                sandbox_dir = ws_router.resolve_session_sandbox_db(
                    db,
                    session_id,
                    session_row.workspace_id,
                    session_row.scope_path,
                )
        except Exception as exc:  # noqa: BLE001 —— 沙箱不可得不阻断回合（旧语义）
            ws_router.agent_trace(f"sandbox resolve failed type={type(exc).__name__}")
        history, trim_meta = ws_router._history_with_trim(db, session_id)
        # #2（V1.74）：窗口裁剪事件化留痕——本回合装配模型上下文时若发生了
        # 窗口裁剪（compact 截断或尾窗截断），落一条 context_trim 持久事件
        # （仅元信息：触发原因/保留策略/被裁范围，不携带被裁原文——观察纪律）。
        # 留痕在回合业务事件之前发出，response.completed 仍为本轮最后一条持久事件。
        if int(trim_meta.get("dropped") or 0) > 0:
            await ws_router._emit_persistent(
                db,
                websocket,
                state,
                session_id,
                "context_trim",
                {
                    "reason": str(trim_meta.get("reason") or "tail_window"),
                    "dropped": int(trim_meta.get("dropped") or 0),
                    "kept": int(trim_meta.get("kept") or 0),
                    "in_scope_total": int(trim_meta.get("in_scope_total") or 0),
                    "keep_from_id": trim_meta.get("keep_from_id"),
                    "limit": int(trim_meta.get("limit") or 0),
                },
                task_id=None,
            )
        compact_summary = (session_row.compact_summary or "") if session_row else ""
        # 核心策略、L2 项目常量和 L3 协议档补充提示词均由受控层组装。除关闭
        # 缓存时的兼容单字符串外，同时保存无密钥的分段来源，供图节点恢复真实
        # S1 → S2 → S5 → S6 缓存边界。
        system_vars = ws_router.SystemVars(
            skill_hints=tuple(ws_router.skill_hint_lines()),
            session_owner=str(session_row.user_id) if session_row else None,
            project_instructions=ws_router.DEFAULT_PROJECT_INSTRUCTIONS,
            agent_prompt_overlay=ws_router.get_agent_prompt_overlay(db, profile.id),
        )
        system_parts = ws_router.build_system_prompt_parts(system_vars)
        system_prompt = ws_router.build_system_prompt(system_vars)
        serializable = ws_router.to_serializable_request(
            ws_router.ModelRequest.from_messages(config, history, system=system_prompt),
            system_context={
                "static_system": system_parts.static_system,
                "skill_hints": system_parts.skill_hints,
                "overlay": system_parts.overlay,
            },
        )
        # 新回合复用租约 ID 作为检查点线程 ID，便于并发与中断审计关联；
        # H5 审批恢复沿用原中断回合的 thread_id（卡 meta 记录）。
        thread_id = resume_thread_id or turn_id or f"{session_id}:{uuid4().hex}"
        # 会话文件沙箱注入（H5 P0；F3/G5）：read/write/edit/bash 以上方统一解析
        # 的沙箱根为执行域（绑定 = 工作区 scope / 未绑定 = legacy）；解析失败时
        # sandbox_dir="" —— 工具保持 fail-closed（旧语义），绝不回落 legacy。
        graph_config = {
            "configurable": {
                # 每回合独立 thread_id：检查点按回合隔离（M3 阶段 3）
                "thread_id": thread_id,
                "abort": {"should_abort": abort.is_set},
                "credentials": {
                    "api_key": config.api_key or "",
                    "user_id": user_id,
                },
                "sandbox": {"dir": sandbox_dir},
                # 资产溯源门禁输入：本会话用户消息引用过的附件集合（空集短路）。
                "assets": {"file_ids": ws_router._session_owned_file_ids(db, session_id)},
                "session": {
                    "id": session_id,
                    # compact 摘要供 M2 assemble 注入【会话摘要】，不入 GraphState
                    "compact_summary": compact_summary,
                },
                # 协议档 ID 用于助手消息头快照，不含密钥。
                "profile": {"id": profile.id},
                # ── Workflow DAG 上下文（H2：节点不触碰 DB，全部由本层注入）──
                "db_factory": ws_router.SessionLocal,  # W6 入队唯一经 worker_bridge
                "session_id": session_id,
                "user_id": user_id,
                # W3 会话占槽门禁探针（惰性调用，避免非 workflow 回合查库）
                "session_probe": ws_router._make_session_probe(session_id),
                # 确认卡回执重放载荷（非空时 W5 合并放行 W6）
                "workflow_confirm": workflow_confirm or {},
            }
        }
        deferred_completed: list[dict] = []

        async for mode, chunk in ws_router._AGENT.astream(
            serializable, config=graph_config, resume=resume
        ):
            if mode == "custom":
                kind = str(chunk.get("kind") or "")
                text = str(chunk.get("text") or "")
                if kind == "content" and text:
                    await ws_router.SESSION_CONNECTION_HUB.broadcast_chunk(
                        session_id,
                        lambda cursor, text=text: ws_router._frame(
                            session_id,
                            "assistant_delta",
                            cursor,
                            {"role": "assistant", "text": text},
                        ),
                    )
                continue
            # H5 HITL：图 interrupt（危险 bash / 提问）——先于事件翻译处理，
            # 落审批卡并广播 tool_approval 事件后暂停回合（不产 completed）。
            interrupts = chunk.get("__interrupt__")
            if interrupts:
                paused = await ws_router._handle_graph_interrupt(
                    db,
                    websocket,
                    state,
                    session_id,
                    interrupts,
                    thread_id=thread_id,
                    user_id=user_id,
                )
                if paused:
                    break
            # updates 模式：按节点边界消费 pending_events，统一 emit；
            # Router 节点一旦执行即捕获审计三元组，供取消/异常收尾携带（O2）
            router_audit = ws_router.router_audit_from_update(chunk) or router_audit
            if turn_sink is not None:
                task_id_hit = ws_router.enqueued_task_id_from_update(chunk)
                if task_id_hit:
                    turn_sink["enqueued_task_id"] = task_id_hit
            for event in ws_router.iter_pending_events(chunk):
                if turn_sink is not None and event.get("kind") == "error":
                    # 确认重放的 runner 依此判断图内已发送业务错误，避免恢复卡后
                    # 再重复推送同一条错误。
                    turn_sink["error"] = dict(event.get("payload") or {})
                    turn_sink["error_emitted"] = True
                if event.get("kind") == "response.completed":
                    # completed 必须是本轮最后一条持久事件。
                    deferred_completed.append(event)
                    continue
                await ws_router._translate_event(
                    db,
                    websocket,
                    state,
                    session_id,
                    profile,
                    event,
                    turn_id=turn_id,
                    thread_id=thread_id,
                    user_id=user_id,
                )
        for event in deferred_completed:
            await ws_router._translate_event(
                db,
                websocket,
                state,
                session_id,
                profile,
                event,
                turn_id=turn_id,
                thread_id=thread_id,
                user_id=user_id,
            )
    except asyncio.CancelledError:
        db.rollback()
        if abort.is_set():
            logger.info("Agent 回合已中止 session=%s", session_id)
            await ws_router._emit_turn_completed(
                db,
                websocket,
                state,
                session_id,
                finish_reason="cancelled",
                turn_id=turn_id,
                router_audit=router_audit,
            )
            return
        raise
    except ws_router.StreamAborted:
        db.rollback()
        logger.info("Agent 回合已中止 session=%s", session_id)
        await ws_router._emit_turn_completed(
            db,
            websocket,
            state,
            session_id,
            finish_reason="cancelled",
            turn_id=turn_id,
            router_audit=router_audit,
        )
    except ws_router.AppError as exc:
        db.rollback()
        logger.info("Agent 回合失败 session=%s code=%s", session_id, exc.code.value)
        if turn_sink is not None:
            turn_sink["error"] = {"code": exc.code.value, "message": exc.message}
            turn_sink["error_emitted"] = True
        await ws_router._emit_error(db, websocket, state, session_id, exc)
        await ws_router._emit_turn_completed(
            db,
            websocket,
            state,
            session_id,
            finish_reason="error",
            turn_id=turn_id,
            router_audit=router_audit,
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Agent 回合内部异常 session=%s type=%s", session_id, type(exc).__name__)
        if turn_sink is not None:
            turn_sink["error"] = {"code": ws_router.ErrorCode.INTERNAL.value, "message": "Agent 调用失败"}
            turn_sink["error_emitted"] = True
        await ws_router._emit_error(
            db,
            websocket,
            state,
            session_id,
            ws_router.AppError(ws_router.ErrorCode.INTERNAL, "Agent 调用失败"),
        )
        await ws_router._emit_turn_completed(
            db,
            websocket,
            state,
            session_id,
            finish_reason="error",
            turn_id=turn_id,
            router_audit=router_audit,
        )
    finally:
        db.close()
