from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from ..core.contracts import AgentTraceEvent
from .state import WorkflowState

Node = Callable[[WorkflowState], Awaitable[WorkflowState]]
Route = Callable[[WorkflowState], str]


class StateGraph:
    """有明确节点、路由和终止状态的异步状态机。"""

    def __init__(self, max_steps: int = 20) -> None:
        self.nodes: dict[str, Node] = {}
        self.routes: dict[str, Route] = {}
        self.max_steps = max_steps

    def add_node(self, name: str, node: Node) -> None:
        if name in self.nodes:
            raise ValueError(f"workflow node already exists: {name}")
        self.nodes[name] = node

    def add_route(self, name: str, route: Route) -> None:
        self.routes[name] = route

    async def run(self, state: WorkflowState) -> WorkflowState:
        for _ in range(self.max_steps):
            if state.node == "complete":
                state.status = "completed"
                return state
            if state.node not in self.nodes:
                state.status = "failed"
                raise RuntimeError(f"workflow node not found: {state.node}")
            node_name = state.node
            started = datetime.now(timezone.utc)
            try:
                state = await self.nodes[node_name](state)
                finished = datetime.now(timezone.utc)
                state.trace_events.append(
                    AgentTraceEvent(
                        agent=node_name,
                        status="completed",
                        started_at=started,
                        finished_at=finished,
                        duration_ms=round(
                            (finished - started).total_seconds() * 1000
                        ),
                    )
                )
            except Exception as exc:
                finished = datetime.now(timezone.utc)
                state.trace_events.append(
                    AgentTraceEvent(
                        agent=node_name,
                        status="failed",
                        started_at=started,
                        finished_at=finished,
                        duration_ms=round(
                            (finished - started).total_seconds() * 1000
                        ),
                        error_code=type(exc).__name__,
                    )
                )
                state.status = "failed"
                raise
            if state.node in self.routes:
                state.node = self.routes[state.node](state)
        state.status = "failed"
        raise RuntimeError("workflow exceeded maximum steps")
