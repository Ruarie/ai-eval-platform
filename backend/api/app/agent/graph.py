"""基于 LangGraph 的 Harness Agent 图（H1：可选 Router 四路分流骨架）。

图拓扑由 ``hybrid_engine_enabled`` 在进程启动时决定：

- **关闭（默认）**：``START → chat_stream → END``，与骨架化纯对话完全一致
  （回归保证：事件序列与 payload 不因本文件引入而漂移）；
- **开启（H1–H4）**：``START → router → direct | chat_stream | workflow | agent``；
  workflow 进入 W0–W7 确定性链，agent 进入 TAOR 子图，并在 H4 接入 ``reflect``
  五档判决回边：``plan → discover → orchestrator ⇄ tools``，``orchestrator``
  停止或守卫截断后一律进 ``reflect``，由它裁决 ``pass`` / ``clarify`` / ``reject``
  收尾，或 ``repair`` 回 ``orchestrator``、``retry`` 回 ``plan``（两档均为回合级
  硬上限）。

节点只返回纯数据（pending_events / response 投影），WebSocket、数据库与
平台任务队列由路由层（ws.py）负责，节点内不持有外部资源（§2.5 事件桥接契约）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from ..config import settings
from ..errors import AppError, ErrorCode
from ..harness.execution import runtime_thread_id
from ..harness.memory import GraphState, SerializableRequest
from ..llm import ModelGateway, ModelResponse
from .graph_routing import (  # noqa: F401  对外重导出
    _after_orchestrator,
    _after_reflect,
    _after_tools,
    _after_workflow_step,
    _has_completed_event,
    _route_by_engine,
)
from .graph_updates import (  # noqa: F401  对外重导出
    enqueued_task_id_from_update,
    iter_pending_events,
    router_audit_from_update,
)
from .router_node import direct_node, router_node
from .routing import chat_stream_node
from .taor_nodes import (
    make_discover_node,
    make_orchestrator_node,
    make_plan_node,
    make_reflect_node,
    make_tools_node,
)
from .workflow_nodes import (
    await_confirm_node,
    build_task_spec_node,
    enqueue_node,
    load_skill_node,
    prepare_slots_node,
    select_skill_node,
    summarize_node,
    validate_gates_node,
    workflow_failure_node,
)

# 混合引擎开启时的递归上限（推导见 _prepare_run_config；关闭时沿用骨架版 32）
_HYBRID_RECURSION_LIMIT = 64














class LangGraphAgent:
    """Harness Agent 图；对外入口与既有 ws.py 调用契约保持一致。"""

    def __init__(
        self,
        gateway: ModelGateway | None = None,
        registry: object | None = None,
        *,
        agent_registry: object | None = None,
        db_factory: object | None = None,
        sandbox_dir: str | None = None,
        user_id: str = "",
        checkpointer: object | None = None,
    ) -> None:
        """创建 Agent 图；网关/注册表/检查点可注入测试夹具。

        H3：``registry``（ToolRegistry）/ ``agent_registry``（AgentRegistry）
        参与 ``engine=agent`` 分支构建——缺省时按默认注册表构建；纯对话
        开关关闭时不构建工具节点，两个注册表参数不参与图。
        """
        self._gateway = gateway or ModelGateway()
        self._registry = registry
        self._agent_registry = agent_registry
        self._db_factory = db_factory
        self._sandbox_dir = sandbox_dir
        self._user_id = user_id
        self._checkpointer = checkpointer
        # 原生工具单回合原文存储（不参与序列化；H5 修复：工具十层链的
        # native 结果回灌依赖本 store，缺失时全部 native 工具被拒）
        from app.harness.execution.native_results import NativeToolResultStore

        self._native_tool_results = NativeToolResultStore()
        self._graph = self._build_graph()

    def _build_graph(self):
        """构建图：主开关关闭保持纯对话；开启接入 Router 四路分流。

        H2：``engine=workflow`` 走 W0–W7 Workflow DAG；
        H3：``engine=agent`` 走 TAOR 子图（plan → discover → orchestrator ⇄ tools）；
        W3/W5 失败与 TAOR 守卫经条件边就地收尾。
        """
        graph = StateGraph(GraphState)
        graph.add_node("chat_stream", self._make_chat_node())
        if not settings.hybrid_engine_enabled:
            graph.add_edge(START, "chat_stream")
            graph.add_edge("chat_stream", END)
        else:
            graph.add_node("router", self._make_router_node())
            graph.add_node("direct", self._make_direct_node())
            graph.add_edge(START, "router")
            graph.add_conditional_edges(
                "router",
                _route_by_engine,
                {
                    "direct": "direct",
                    "chat_stream": "chat_stream",
                    "workflow": "workflow",
                    "plan": "plan",
                },
            )
            graph.add_edge("direct", END)
            graph.add_edge("chat_stream", END)
            self._add_workflow_dag(graph)
            self._add_agent_subgraph(graph)
        # 阶段 3：Checkpointer 按 thread_id 隔离回合（M3-D4 恢复语义）
        if self._checkpointer is not None:
            return graph.compile(checkpointer=self._checkpointer)
        return graph.compile()

    def _add_agent_subgraph(self, graph: StateGraph) -> None:
        """H3 TAOR 子图 + H4 reflect 判决回边（单图内循环，全部硬上限有界）。

        拓扑：``plan → discover → orchestrator ⇄ tools``；``orchestrator`` 停止后
        进 ``reflect``，后者可回 ``orchestrator``（repair）或 ``plan``（retry）。
        """
        from app.harness.execution.registry import build_default_registry
        from app.harness.execution.toolnode import build_tool_node
        from app.harness.orchestration.agents import get_default_agent_registry

        tool_registry = self._registry or build_default_registry()
        agent_registry = self._agent_registry or get_default_agent_registry()
        tools_node = build_tool_node(
            tool_registry,  # type: ignore[arg-type]
            db_factory=self._db_factory,  # type: ignore[arg-type]
            sandbox_dir=self._sandbox_dir,
            user_id=self._user_id,
            native_tool_results=self._native_tool_results,
        )
        graph.add_node("plan", make_plan_node(self._gateway))
        graph.add_node("discover", make_discover_node(agent_registry, tool_registry))
        graph.add_node(
            "orchestrator",
            make_orchestrator_node(
                self._gateway,
                agent_registry,
                tool_registry,
                native_tool_results=self._native_tool_results,
            ),
        )
        graph.add_node("tools", make_tools_node(tools_node))
        graph.add_node("reflect", make_reflect_node(self._gateway))
        graph.add_edge("plan", "discover")
        graph.add_edge("discover", "orchestrator")
        graph.add_conditional_edges(
            "orchestrator",
            _after_orchestrator,
            {"tools": "tools", "reflect": "reflect"},
        )
        graph.add_conditional_edges(
            "reflect",
            _after_reflect,
            {"orchestrator": "orchestrator", "plan": "plan", "END": END},
        )
        graph.add_conditional_edges(
            "tools",
            _after_tools,
            {"tools": "tools", "orchestrator": "orchestrator", "END": END},
        )

    def _add_workflow_dag(self, graph: StateGraph) -> None:
        """W0–W7 八节点确定性链（H2；失败条件边就地收尾，无重试回环）。"""
        workflow_nodes = {
            "w0_select_skill": select_skill_node,
            "w1_prepare_slots": prepare_slots_node,
            "w2_load_skill": load_skill_node,
            "w3_validate_gates": validate_gates_node,
            "w4_build_task_spec": build_task_spec_node,
            "w5_await_confirm": await_confirm_node,
            "w6_enqueue": enqueue_node,
            "w7_summarize": summarize_node,
        }
        graph.add_node("workflow", self._make_workflow_entry())
        graph.add_node("workflow_failure", workflow_failure_node)
        for node_name, node_fn in workflow_nodes.items():
            graph.add_node(node_name, node_fn)
        graph.add_edge("workflow", "w0_select_skill")
        graph.add_conditional_edges(
            "w0_select_skill",
            lambda state: _after_workflow_step(state, "w1_prepare_slots"),
            {"w1_prepare_slots": "w1_prepare_slots", "workflow_failure": "workflow_failure", "END": END},
        )
        graph.add_conditional_edges(
            "w1_prepare_slots",
            lambda state: _after_workflow_step(state, "w2_load_skill"),
            {"w2_load_skill": "w2_load_skill", "workflow_failure": "workflow_failure", "END": END},
        )
        graph.add_conditional_edges(
            "w2_load_skill",
            lambda state: _after_workflow_step(state, "w3_validate_gates"),
            {"w3_validate_gates": "w3_validate_gates", "workflow_failure": "workflow_failure", "END": END},
        )
        graph.add_conditional_edges(
            "w3_validate_gates",
            lambda state: _after_workflow_step(state, "w4_build_task_spec"),
            {"w4_build_task_spec": "w4_build_task_spec", "workflow_failure": "workflow_failure", "END": END},
        )
        graph.add_conditional_edges(
            "w4_build_task_spec",
            lambda state: _after_workflow_step(state, "w5_await_confirm"),
            {"w5_await_confirm": "w5_await_confirm", "workflow_failure": "workflow_failure", "END": END},
        )
        graph.add_conditional_edges(
            "w5_await_confirm",
            lambda state: _after_workflow_step(state, "w6_enqueue"),
            {"w6_enqueue": "w6_enqueue", "workflow_failure": "workflow_failure", "END": END},
        )
        graph.add_conditional_edges(
            "w6_enqueue",
            lambda state: _after_workflow_step(state, "w7_summarize"),
            {"w7_summarize": "w7_summarize", "workflow_failure": "workflow_failure", "END": END},
        )
        graph.add_edge("w7_summarize", END)
        graph.add_edge("workflow_failure", END)

    def _make_workflow_entry(self):
        """Workflow 入口占位节点：透传 Router 分流结论（engine 本轮不可变）。"""

        def node(state: GraphState) -> dict:
            return {"workflow_step": "w0_select_skill"}

        return node

    def _make_chat_node(self):
        """闭包绑定网关的 Chat 流式节点（节点签名只接收 state）。"""
        gateway = self._gateway

        def node(state: GraphState) -> dict:
            return chat_stream_node(state, gateway)

        return node

    def _make_router_node(self):
        """闭包绑定网关的 Router 分流节点（L0 零调用；L1 仅低置信时短调用）。"""
        gateway = self._gateway

        def node(state: GraphState) -> dict:
            return router_node(state, gateway)

        return node

    @staticmethod
    def _make_direct_node():
        """direct 防御节点（纯函数，不绑定网关：零模型调用）。"""

        def node(state: GraphState) -> dict:
            return direct_node(state)

        return node

    def invoke(self, request: SerializableRequest, config: dict | None = None) -> ModelResponse:
        """执行一轮非流式 Agent 调用（纯对话路径产生模型响应）。"""
        run_config, thread_id = self._prepare_run_config(config)
        try:
            state = self._graph.invoke({"request": request}, config=run_config)
            return self._response_from_state(state)
        finally:
            self._discard_thread(thread_id)

    async def astream(
        self,
        request: SerializableRequest,
        config: dict | None = None,
        *,
        resume: object | None = None,
    ) -> AsyncIterator[tuple[str, dict]]:
        """执行一轮流式 Agent 调用。

        产出 ``(mode, chunk)`` 二元组：
        - ``mode="custom"``：模型正文增量（瞬态帧）；
        - ``mode="updates"``：节点增量（含 pending_events，收包循环统一 emit）。
        """
        from langgraph.types import Command

        graph_input: object
        if resume is not None:
            graph_input = Command(resume=resume)
        else:
            graph_input = {"request": request}
        run_config, thread_id = self._prepare_run_config(config)
        try:
            async for mode, chunk in self._graph.astream(
                graph_input,
                config=run_config,
                stream_mode=["custom", "updates"],
            ):
                yield mode, chunk
        finally:
            await self._discard_thread_guarded(thread_id)

    async def ahas_pending_interrupt(self, thread_id: str) -> bool:
        """判断 thread 是否仍停在待恢复的人工中断处（H5）。

        判定依据为编译图 ``aget_state(config).next``：interrupt 暂停的线程
        保留待恢复节点（next 非空），正常完成的回合 next 为空；本仓库所用
        LangGraph 版本不把 pending_interrupts 写入检查点元数据，故不用
        metadata 判定。无检查点或读取失败一律返回 False（安全默认：不因
        检查点异常阻塞主流程）。
        """
        checkpointer = getattr(self._graph, "checkpointer", None)
        if checkpointer is None:
            return False
        config = {"configurable": {"thread_id": thread_id}}
        try:
            snapshot = await self._graph.aget_state(config)
        except Exception:  # noqa: BLE001 —— 检查点异常不阻塞恢复判定主流程
            return False
        return bool(getattr(snapshot, "next", ()))

    @staticmethod
    def _prepare_run_config(config: dict | None) -> tuple[dict, str]:
        """复制运行配置并保证每一轮都有不可冲突的临时存储键。"""
        run_config = dict(config or {})
        configurable = dict(run_config.get("configurable") or {})
        thread_id = runtime_thread_id(configurable)
        if not thread_id:
            thread_id = f"agent:{uuid4().hex}"
            configurable["thread_id"] = thread_id
        run_config["configurable"] = configurable
        # H4：agent 分支新增 repair / retry 两条回边，超级步上界由「2（plan+discover）
        # + 2×MAX_REPLANS（重规划回边）+ 2×tool_turns 上限（20）」推导 ≈ 46，
        # 取 64 预留余量；真正的硬上限仍是回合预算与 MAX_REPAIRS / MAX_REPLANS。
        run_config.setdefault(
            "recursion_limit",
            _HYBRID_RECURSION_LIMIT if settings.hybrid_engine_enabled else 32,
        )
        return run_config, thread_id

    def _discard_thread(self, thread_id: str) -> None:
        """回合结束清理单回合原生工具原文（进程内 store，不序列化）。"""

    async def _discard_thread_guarded(self, thread_id: str) -> None:
        """H5：中断暂停的回合保留单回合原文（resume 继续执行需要）；仅
        无待恢复中断（回合正常结束/异常）时清理，避免 resume 后模型
        上下文丢失原生工具原文。"""
        if self._checkpointer is not None:
            try:
                if await self.ahas_pending_interrupt(thread_id):
                    return
            except Exception:  # noqa: BLE001 —— 判定失败按可清理处理
                pass
        self._native_tool_results.clear(thread_id)

    @staticmethod
    def _response_from_state(state: dict) -> ModelResponse:
        """从图终态提取模型响应（state.response 为可序列化投影）。"""
        response = state.get("response")
        if not isinstance(response, dict):
            raise AppError(ErrorCode.INTERNAL, "Agent 未产生有效响应")
        return ModelResponse(
            text=str(response.get("text", "")),
            usage=response.get("usage") or {},
            latency_ms=int(response.get("latency_ms", 0)),
        )






