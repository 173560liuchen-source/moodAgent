from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import ChatMessage


RiskLevel = Literal["low", "medium", "high"]
SafetyDecisionName = Literal["allow", "redact", "block", "escalate"]
RAGExpectation = Literal["required", "none_expected", "optional"]
FaultMode = Literal["none", "model_api_failure", "model_timeout", "invalid_json", "rag_failure"]
ExpectedRoute = Literal[
    "exploratory_support",
    "knowledge_support",
    "structured_assessment",
    "follow_up_support",
    "crisis_response",
]


class RedTeamExpectation(BaseModel):
    """单条红队样本的机器可验证期望。

    这里保存的是合成测试期望，不保存真实用户聊天。
    """

    model_config = ConfigDict(extra="forbid")

    crisis_level: RiskLevel = "low"
    min_crisis_level: RiskLevel | None = None
    safety_decision: SafetyDecisionName | None = None
    requires_human_review: bool | None = None
    pii_types: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    accepted_emotions: list[str] = Field(default_factory=list)
    rag: RAGExpectation = "optional"
    expected_rag_categories: list[str] = Field(default_factory=list)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    required_concepts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    should_abstain: bool | None = None
    model_failure_expected: bool = False
    fallback_expected: bool = False
    inject_fault: FaultMode = "none"
    expected_route: ExpectedRoute | None = None


class RedTeamCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    context_metadata: dict[str, Any] = Field(default_factory=dict)
    expectation: RedTeamExpectation
    tags: list[str] = Field(default_factory=list)


class RedTeamRunRequest(BaseModel):
    """红队评测运行参数。

    categories/tags/case_ids 为空时默认跑全部内置样本。
    """

    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)
    max_cases: int | None = Field(default=None, ge=1, le=200)
    include_raw_outputs: bool = False
    timeout_seconds_per_case: float = Field(default=45.0, ge=5.0, le=180.0)
    # Accepted only by the offline evaluation runner; main API requests never use it.
    ablation: dict[str, bool] = Field(default_factory=dict)


class RedTeamCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: str
    passed: bool
    latency_ms: int
    assertions: dict[str, bool | None] = Field(default_factory=dict)
    failed_assertions: list[str] = Field(default_factory=list)
    crisis_safety_passed: bool | None = None
    observed: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    raw_output: dict[str, Any] | None = None


class RedTeamMetricReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    crisis_safety_pass_rate: float | None = None
    crisis_recall: float | None = None
    high_risk_miss_rate: float | None = None
    false_positive_rate: float | None = None
    emotion_consistency: float | None = None
    json_valid_rate: float | None = None
    rag_citation_accuracy: float | None = None
    rag_expectation_pass_rate: float | None = None
    rag_category_recall: float | None = None
    rag_document_recall_at_5: float | None = None
    rag_chunk_recall_at_5: float | None = None
    rag_mrr_at_5: float | None = None
    rag_citation_precision: float | None = None
    rag_citation_completeness: float | None = None
    rag_groundedness: float | None = None
    rag_abstention_accuracy: float | None = None
    rag_retrieval_error_rate: float | None = None
    average_latency_ms: float | None = None
    model_failure_fallback_success_rate: float | None = None
    human_review_consistency: float | None = None
    trace_order_consistency: float | None = None
    trace_completeness: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    max_latency_ms: int | None = None
    timeout_rate: float | None = None
    route_accuracy: float | None = None


class RedTeamEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_version: str = "9.0.0"
    target: str = "moodapp-langgraph-orchestrator"
    metrics: RedTeamMetricReport
    cases: list[RedTeamCaseResult]
    ablation: dict[str, bool] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
