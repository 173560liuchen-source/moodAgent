from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    """跨智能体共享的请求上下文；不保存业务数据。"""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: int | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTraceEvent(BaseModel):
    agent: str
    status: Literal["started", "completed", "failed", "skipped"]
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    error_code: str | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentErrorResponse(BaseModel):
    request_id: str
    code: str
    message: str
    retryable: bool = False


class AgentEnvelope(BaseModel):
    request_id: str
    status: Literal["completed", "partial", "failed"]
    data: dict[str, Any] = Field(default_factory=dict)
    trace: list[AgentTraceEvent] = Field(default_factory=list)
    audit_id: str | None = None


def java_to_internal_score(value: int | float | None) -> float:
    """将 Java 的 0-100 分数转换为 Python 内部的 0-1 分数。"""
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value) / 100.0))


def internal_to_java_score(value: int | float | None) -> int:
    """将 Python 内部的 0-1 分数转换为 Java 需要的 0-100 整数。"""
    if value is None:
        return 0
    return round(max(0.0, min(1.0, float(value))) * 100)
