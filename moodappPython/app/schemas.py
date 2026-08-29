from typing import Any, Literal

from pydantic import BaseModel, Field

from .core.contracts import AgentContext


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ModelChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=2048)


class ModelChatResponse(BaseModel):
    content: str
    model: str
    # DeepSeek 的 usage 中包含嵌套对象，例如 cached_tokens、reasoning_tokens。
    usage: dict[str, Any] | None = None


class ChatAgentRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatAgentResponse(BaseModel):
    agent: str = "chat"
    content: str
    model: str
    usage: dict[str, Any] | None = None


class EmotionAgentRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


class CrisisAgentRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


class OrchestrationRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    context: AgentContext = Field(default_factory=AgentContext)


class TrendAgentRequest(BaseModel):
    points: list[dict] = Field(default_factory=list)


class RiskAgentRequest(BaseModel):
    crisis: dict = Field(default_factory=dict)
    emotion: dict = Field(default_factory=dict)
    trend: dict | None = None
    rag: dict | None = None


class SafetyGateEndpointRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


class RAGSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=12000)
    history: list[ChatMessage] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.2, ge=0.0, le=1.0)


class AssessmentReportRequest(BaseModel):
    """SDS 测评完成后生成报告的最小输入，不承载身份或原始聊天内容。"""

    score: int = Field(ge=20, le=80)
    level: str = Field(min_length=1, max_length=40)
    answers: list[int] = Field(default_factory=list, max_length=20)


class AssessmentReportResponse(BaseModel):
    emotionalAnalysis: str
    physicalSymptoms: str
    cognitiveStatus: str
    suggestions: str
    summary: str
    model: str
    usage: dict[str, Any] | None = None
