"""Harness 图的条件边路由（纯状态判断，不依赖图实例）。

抽出后由 ``graph.LangGraphAgent`` 装配条件边；测试可直接对函数断言分支。
"""

from __future__ import annotations

from ..harness.memory import GraphState


def _route_by_engine(state: GraphState) -> str:
    """Router 之后的顶层条件边：direct 零模型收尾，workflow 进 DAG，
    agent 进 TAOR 子图，其余降级 chat。

    防御语义：Router 未产出 ``engine``（异常路径）时回落 chat，不猜测。
    """
    engine = state.get("engine")
    if engine == "direct":
        return "direct"
    if engine == "workflow":
        return "workflow"
    if engine == "agent":
        return "plan"
    return "chat_stream"


def _after_orchestrator(state: GraphState) -> str:
    """TAOR：Act 未决（有 pending_tool）→ tools；停止或守卫截断 → reflect 判决。

    H4：模型自主停止与守卫截断都不再直接 END——一律先进 reflect，由它决定
    放行（pass）/ 提问（clarify）/ 收尾（reject）/ 修复（repair）/ 重规划（retry）。
    「模型觉得差不多了」不是停止条件（ADR-2）。

    注意：本分支**不读** ``workflow_failed``（那是 Workflow DAG（W0–W7）专用
    语义字段，TAOR 子图内 orchestrator/tools 都不会置位；条件边映射也没有
    END 键——若误置会触发 LangGraph Invalid path 而非收尾，属假守卫）。
    """
    if state.get("pending_tool"):
        return "tools"
    return "reflect"


def _after_reflect(state: GraphState) -> str:
    """H4：reflect 五档判决的回边与收尾。

    ``repair`` 回 orchestrator（失败阶梯首档，最多 MAX_REPAIRS 次）；
    ``retry`` 回 plan（有界重规划，最多 MAX_REPLANS 次）；
    ``pass`` / ``clarify`` / ``reject`` 一律 END（三档都是终态，不再回圈）。
    """
    verdict = state.get("verdict")
    if verdict == "repair":
        return "orchestrator"
    if verdict == "retry":
        return "plan"
    return "END"


def _after_tools(state: GraphState) -> str:
    """TAOR：工具执行后回 orchestrator 看 Observation；队列仍有待执行项时自环
    tools（F0/P2 原生 Act 可一次产多个 tool_use，pending_tool/pending_tools
    drain 由 tools 节点自环完成，全部终态才回 orchestrator 消费回填轮）。"""
    if state.get("turn_failed") or state.get("workflow_failed"):
        return "END"
    if state.get("pending_tool"):
        return "tools"
    return "orchestrator"


def _has_completed_event(state: GraphState) -> bool:
    """判断节点是否已经自行写入回合结束事件。"""
    return any(
        isinstance(event, dict) and event.get("kind") == "response.completed"
        for event in state.get("pending_events") or ()
    )


def _after_workflow_step(state: GraphState, success_node: str) -> str:
    """失败链路统一补 completed；已自行收尾的 W5 直接结束。

    ``workflow_failed`` 是所有 Workflow 节点的共同失败标记。只有 W5 的
    确认卡/补槽分支会自行发送 ``response.completed``；其余失败经
    ``workflow_failure`` 统一收尾，避免 WS 前端一直等待本轮结束。
    """
    if not state.get("workflow_failed"):
        return success_node
    return "END" if _has_completed_event(state) else "workflow_failure"
