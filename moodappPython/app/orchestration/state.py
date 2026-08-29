from dataclasses import dataclass, field
from typing import Any

from ..core.contracts import AgentContext, AgentTraceEvent
from ..schemas import OrchestrationRequest


@dataclass
class WorkflowState:
    request: OrchestrationRequest
    context: AgentContext
    node: str = "safety_gate"
    status: str = "running"
    trace: list[str] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)
    trace_events: list[AgentTraceEvent] = field(default_factory=list)
