from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..core.contracts import AgentContext, AgentTraceEvent
from .crisis_agent import CrisisAnalysis
from .emotion_agent import EmotionAnalysis
from .evaluator_agent import EvaluationAnalysis
from .intervention_agent import InterventionAnalysis
from .profile_agent import ProfileAnalysis
from .rag_agent import RAGAnalysis
from .risk_agent import RiskAnalysis
from .safety_gate import SafetyDecision
from .trend_agent import TrendAnalysis


class AuditDecisionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    safety_decision: str | None = None
    crisis_level: str | None = None
    crisis_action: str | None = None
    emotion_label: str | None = None
    intervention_level: str | None = None
    trend_stress_direction: str | None = None
    risk_level: str | None = None
    risk_score: float | None = None
    evaluator_action: str | None = None
    evaluator_passed: bool | None = None
    final_reply_corrected: bool = False
    requires_human_review: bool = False


class AuditVersionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_engine: str
    workflow_version: str
    agent_versions: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)


class AuditDataMinimization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_message_stored: bool = False
    full_history_stored: bool = False
    message_hash: str
    redacted_message_hash: str | None = None
    history_count: int = Field(ge=0)
    persisted_by_python: bool = False


class AuditTraceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_sequence: list[str] = Field(default_factory=list)
    route: str | None = None
    trace_event_count: int = Field(ge=0)
    failed_nodes: list[str] = Field(default_factory=list)
    total_duration_ms: int | None = Field(default=None, ge=0)


class AuditRoutingSnapshot(BaseModel):
    """风险约束路由的可审计快照，不保存用户原文。"""

    model_config = ConfigDict(extra="forbid")

    selected_route: str | None = None
    policy_version: str | None = None
    reasons: list[str] = Field(default_factory=list)
    features: dict[str, str | int | float | bool] = Field(default_factory=dict)
    route_scores: dict[str, float] = Field(default_factory=dict)
    rag_needed: bool = False
    evidence_sufficient: bool = False
    hard_constraint_triggered: bool = False


class AuditEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crisis_evidence_count: int = Field(ge=0)
    emotion_evidence_count: int = Field(ge=0)
    rag_chunk_ids: list[str] = Field(default_factory=list)
    profile_patch_count: int = Field(ge=0)
    intervention_action_types: list[str] = Field(default_factory=list)
    evaluator_issue_codes: list[str] = Field(default_factory=list)
    trend_evidence_count: int = Field(default=0, ge=0)
    risk_factor_count: int = Field(default=0, ge=0)


class AuditAnalysis(BaseModel):
    """完整可解释决策链。

    注意：该结构不保存原始完整聊天文本，只保存 hash、版本、决策和证据摘要。
    Java 后端如需持久化，应保存本结构而不是保存 Python 中间原文。
    """

    model_config = ConfigDict(extra="forbid")

    agent: str = "audit"
    audit_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    status: Literal["completed", "partial", "failed"]
    versions: AuditVersionSnapshot
    data_minimization: AuditDataMinimization
    decisions: AuditDecisionSnapshot
    trace_summary: AuditTraceSummary
    routing: AuditRoutingSnapshot
    evidence_summary: AuditEvidenceSummary
    compliance_flags: list[str] = Field(default_factory=list)
    handoff_recommended: bool = False
    prompt_version: str = "audit-agent-rules-6.6.0"


class AuditAgent:
    """审计智能体。

    职责：
    - 汇总每次编排的版本、节点、决策和关键证据；
    - 支持评委查看“系统为什么这么答”；
    - 不保存原始完整聊天文本；
    - 不修改业务决策，只生成审计链。
    """

    name = "audit"
    version = "6.6.0"

    def create_audit(
        self,
        *,
        context: AgentContext,
        original_message: str,
        redacted_message: str | None,
        history_count: int,
        workflow_engine: str,
        workflow_version: str,
        trace: list[str],
        trace_events: list[AgentTraceEvent],
        route: str | None = None,
        route_decision: dict[str, Any] | None = None,
        agent_versions: dict[str, str],
        prompt_versions: dict[str, str],
        safety: SafetyDecision | None = None,
        crisis: CrisisAnalysis | None = None,
        emotion: EmotionAnalysis | None = None,
        rag: RAGAnalysis | None = None,
        trend: TrendAnalysis | None = None,
        risk: RiskAnalysis | None = None,
        profile: ProfileAnalysis | None = None,
        intervention: InterventionAnalysis | None = None,
        evaluator: EvaluationAnalysis | None = None,
        status: Literal["completed", "partial", "failed"] = "completed",
    ) -> AuditAnalysis:
        requires_human = bool(
            (safety and safety.requires_human)
            or (crisis and crisis.requires_human_review)
            or (intervention and intervention.requires_human_review)
            or (evaluator and evaluator.requires_human_review)
        )
        compliance_flags = self._compliance_flags(
            safety=safety,
            crisis=crisis,
            rag=rag,
            profile=profile,
            intervention=intervention,
            evaluator=evaluator,
        )
        routing = self._routing_snapshot(route, route_decision)
        if routing.hard_constraint_triggered:
            compliance_flags.append("risk_router_hard_constraint")
        return AuditAnalysis(
            audit_id=self._audit_id(context.request_id),
            request_id=context.request_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            versions=AuditVersionSnapshot(
                workflow_engine=workflow_engine,
                workflow_version=workflow_version,
                agent_versions=agent_versions,
                prompt_versions=prompt_versions,
            ),
            data_minimization=AuditDataMinimization(
                message_hash=self._hash(original_message),
                redacted_message_hash=self._hash(redacted_message) if redacted_message is not None else None,
                history_count=history_count,
            ),
            decisions=AuditDecisionSnapshot(
                safety_decision=safety.decision if safety else None,
                crisis_level=crisis.level if crisis else None,
                crisis_action=crisis.action if crisis else None,
                emotion_label=emotion.emotion if emotion else None,
                intervention_level=intervention.intervention_level if intervention else None,
                trend_stress_direction=trend.stress_trend if trend else None,
                risk_level=risk.risk_level if risk else None,
                risk_score=risk.risk_score if risk else None,
                evaluator_action=evaluator.action if evaluator else None,
                evaluator_passed=evaluator.passed if evaluator else None,
                final_reply_corrected=bool(evaluator and evaluator.corrected_reply),
                requires_human_review=requires_human,
            ),
            trace_summary=AuditTraceSummary(
                node_sequence=trace,
                route=route,
                trace_event_count=len(trace_events),
                failed_nodes=[event.agent for event in trace_events if event.status == "failed"],
                total_duration_ms=self._total_duration_ms(trace_events),
            ),
            routing=routing,
            evidence_summary=AuditEvidenceSummary(
                crisis_evidence_count=len(crisis.evidence) if crisis else 0,
                emotion_evidence_count=len(emotion.evidence) if emotion else 0,
                rag_chunk_ids=[citation.chunk_id for citation in (rag.citations if rag else [])],
                profile_patch_count=len(profile.patch_items) if profile else 0,
                intervention_action_types=[
                    action.action_type for action in (intervention.actions if intervention else [])
                ],
                evaluator_issue_codes=[issue.code for issue in (evaluator.issues if evaluator else [])],
                trend_evidence_count=len(trend.evidence) if trend else 0,
                risk_factor_count=len(risk.main_factors) if risk else 0,
            ),
            compliance_flags=compliance_flags,
            handoff_recommended=requires_human,
        )

    @staticmethod
    def _routing_snapshot(
        route: str | None,
        route_decision: dict[str, Any] | None,
    ) -> AuditRoutingSnapshot:
        decision = route_decision if isinstance(route_decision, dict) else {}
        raw_features = decision.get("features")
        features = {
            str(key): value
            for key, value in (raw_features.items() if isinstance(raw_features, dict) else [])
            if isinstance(value, (str, int, float, bool)) and not isinstance(value, bytes)
        }
        raw_scores = decision.get("route_scores")
        scores = {
            str(key): float(value)
            for key, value in (raw_scores.items() if isinstance(raw_scores, dict) else [])
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        raw_reasons = decision.get("reasons")
        return AuditRoutingSnapshot(
            selected_route=decision.get("route") or route,
            policy_version=decision.get("policy_version"),
            reasons=[str(reason) for reason in raw_reasons] if isinstance(raw_reasons, list) else [],
            features=features,
            route_scores=scores,
            rag_needed=bool(decision.get("rag_needed", False)),
            evidence_sufficient=bool(decision.get("evidence_sufficient", False)),
            hard_constraint_triggered=bool(decision.get("hard_constraint_triggered", False)),
        )

    @staticmethod
    def _hash(value: str | None) -> str:
        clean = value or ""
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()

    @staticmethod
    def _audit_id(request_id: str) -> str:
        return "audit_" + hashlib.sha256(
            f"{request_id}:moodapp-audit".encode("utf-8")
        ).hexdigest()[:24]

    @staticmethod
    def _total_duration_ms(trace_events: list[AgentTraceEvent]) -> int | None:
        durations = [event.duration_ms for event in trace_events if event.duration_ms is not None]
        if not durations:
            return None
        return sum(durations)

    @staticmethod
    def _compliance_flags(
        *,
        safety: SafetyDecision | None,
        crisis: CrisisAnalysis | None,
        rag: RAGAnalysis | None,
        profile: ProfileAnalysis | None,
        intervention: InterventionAnalysis | None,
        evaluator: EvaluationAnalysis | None,
    ) -> list[str]:
        flags = [
            "data_minimization",
            "no_raw_chat_in_audit",
            "java_owns_persistence",
        ]
        if safety:
            flags.append(f"safety_{safety.decision}")
        if crisis and crisis.level == "high":
            flags.append("high_risk_safety_first")
        if rag:
            flags.append("rag_has_evidence" if rag.has_evidence else "rag_no_evidence_declared")
        if profile and profile.control_policy.python_stores_full_chat is False:
            flags.append("profile_user_control_enabled")
        if intervention and intervention.requires_human_review:
            flags.append("human_review_recommended")
        if evaluator:
            flags.append("final_reply_evaluated")
            if evaluator.corrected_reply:
                flags.append("final_reply_corrected")
        return flags
