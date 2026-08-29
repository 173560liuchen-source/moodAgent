from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RouteName = Literal[
    "exploratory_support",
    "knowledge_support",
    "structured_assessment",
    "follow_up_support",
    "crisis_response",
]


class RoutingInput(BaseModel):
    """De-identified, normalized signals used by the route policy."""

    model_config = ConfigDict(extra="forbid")

    crisis_level: Literal["low", "medium", "high"] = "low"
    crisis_action: str = "normal_support"
    safety_escalated: bool = False
    emotion_load: float = Field(default=0.0, ge=0.0, le=1.0)
    trend_load: float = Field(default=0.0, ge=0.0, le=1.0)
    knowledge_need: float = Field(default=0.0, ge=0.0, le=1.0)
    follow_up_need: float = Field(default=0.0, ge=0.0, le=1.0)
    assessment_evidence: bool = False
    user_turn_count: int = Field(default=0, ge=0)


class RouteScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploratory_support: float = Field(ge=0.0, le=1.0)
    knowledge_support: float = Field(ge=0.0, le=1.0)
    structured_assessment: float = Field(ge=0.0, le=1.0)
    follow_up_support: float = Field(ge=0.0, le=1.0)
    crisis_response: float = Field(ge=0.0, le=1.0)


class RiskConstrainedRouteDecision(BaseModel):
    """Explainable output of the risk-constrained route policy."""

    model_config = ConfigDict(extra="forbid")

    route: RouteName
    features: RoutingInput
    route_scores: RouteScores
    reasons: list[str] = Field(default_factory=list)
    evidence_sufficient: bool
    rag_needed: bool
    hard_constraint_triggered: bool = False
    policy_version: str = "risk-constrained-router-1.1.0"


class RiskConstrainedRouter:
    """Safety-first, score-based policy for selecting one workflow route.

    This is intentionally deterministic: thresholds and weights can be audited and
    calibrated against a fixed evaluation set without exposing raw conversations.
    """

    version = "1.1.0"
    STRUCTURED_ASSESSMENT_THRESHOLD = 0.55
    KNOWLEDGE_SUPPORT_THRESHOLD = 0.55
    FOLLOW_UP_THRESHOLD = 0.60

    @staticmethod
    def _clamp(value: float) -> float:
        return round(min(1.0, max(0.0, value)), 4)

    def decide(self, signals: RoutingInput) -> RiskConstrainedRouteDecision:
        crisis_hard_constraint = (
            signals.safety_escalated
            or signals.crisis_level == "high"
            or signals.crisis_action == "crisis_response"
        )
        if crisis_hard_constraint:
            return RiskConstrainedRouteDecision(
                route="crisis_response",
                features=signals,
                route_scores=RouteScores(
                    exploratory_support=0.0,
                    knowledge_support=0.0,
                    structured_assessment=0.0,
                    follow_up_support=0.0,
                    crisis_response=1.0,
                ),
                reasons=["触发危机安全硬约束，禁止进入普通对话和常规干预路径"],
                evidence_sufficient=True,
                rag_needed=False,
                hard_constraint_triggered=True,
            )

        medium_safety_signal = (
            signals.crisis_level == "medium"
            or signals.crisis_action == "check_in"
        )
        follow_up_score = self._clamp(
            0.75 * signals.follow_up_need + 0.15 * signals.trend_load + 0.10 * signals.emotion_load
        )
        assessment_score = self._clamp(
            0.35 * signals.emotion_load
            + 0.25 * signals.trend_load
            + (0.55 if signals.assessment_evidence else 0.0)
        )
        knowledge_score = self._clamp(0.85 * signals.knowledge_need + 0.15 * signals.emotion_load)
        if medium_safety_signal:
            # A confirmed medium-risk signal is itself sufficient safety evidence.
            # It should not remain in ordinary exploratory dialogue, and curated
            # school/crisis resources are retrieved to avoid invented referrals.
            assessment_score = max(assessment_score, 0.75)
            knowledge_score = max(knowledge_score, 0.65)
        exploratory_score = self._clamp(
            1.0 - max(follow_up_score, assessment_score, knowledge_score)
        )
        scores = RouteScores(
            exploratory_support=exploratory_score,
            knowledge_support=knowledge_score,
            structured_assessment=assessment_score,
            follow_up_support=follow_up_score,
            crisis_response=0.0,
        )

        if medium_safety_signal:
            return RiskConstrainedRouteDecision(
                route="structured_assessment",
                features=signals,
                route_scores=scores,
                reasons=["中风险安全信号需要进一步核查、人工关注与可信支持资源"],
                evidence_sufficient=True,
                rag_needed=True,
            )
        if follow_up_score >= self.FOLLOW_UP_THRESHOLD:
            return RiskConstrainedRouteDecision(
                route="follow_up_support",
                features=signals,
                route_scores=scores,
                reasons=["检测到历史方案及本轮执行效果反馈"],
                evidence_sufficient=True,
                rag_needed=knowledge_score >= self.KNOWLEDGE_SUPPORT_THRESHOLD,
            )
        if knowledge_score >= self.KNOWLEDGE_SUPPORT_THRESHOLD:
            return RiskConstrainedRouteDecision(
                route="knowledge_support",
                features=signals,
                route_scores=scores,
                reasons=["用户本轮明确需要方法、知识、资源或预约信息"],
                evidence_sufficient=False,
                rag_needed=True,
            )
        if (
            signals.assessment_evidence
            and assessment_score >= self.STRUCTURED_ASSESSMENT_THRESHOLD
        ):
            return RiskConstrainedRouteDecision(
                route="structured_assessment",
                features=signals,
                route_scores=scores,
                reasons=["情绪负荷、纵向趋势或测评证据达到综合评估阈值"],
                evidence_sufficient=True,
                rag_needed=knowledge_score >= self.KNOWLEDGE_SUPPORT_THRESHOLD,
            )
        return RiskConstrainedRouteDecision(
            route="exploratory_support",
            features=signals,
            route_scores=scores,
            reasons=["当前没有足够的评估或知识检索需求，进入探索式陪伴"],
            evidence_sufficient=False,
            rag_needed=False,
        )
