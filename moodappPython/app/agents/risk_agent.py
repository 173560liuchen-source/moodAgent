from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .crisis_agent import CrisisAnalysis
from .emotion_agent import EmotionAnalysis
from .rag_agent import RAGAnalysis
from .trend_agent import TrendAnalysis


class RiskCalculationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    formula: str
    value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    contribution: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class RiskRecommendationGrounding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    content_excerpt: str = Field(min_length=1, max_length=240)
    score: float = Field(ge=0.0, le=1.0)
    usage: Literal["recommendation_explanation"] = "recommendation_explanation"


class RiskAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: Literal["low", "attention", "medium", "high"]
    risk_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    emotion_risk: float = Field(ge=0.0, le=1.0)
    trend_risk: float = Field(ge=0.0, le=1.0)
    crisis_detected: bool
    evidence: list[str] = Field(default_factory=list)
    main_factors: list[str] = Field(default_factory=list)
    recommendation: str
    requires_human_review: bool = False
    hard_rule_applied: bool = False
    calculation_trace: list[RiskCalculationItem] = Field(default_factory=list)
    recommendation_grounding: list[RiskRecommendationGrounding] = Field(default_factory=list)
    rag_citations_used: list[str] = Field(default_factory=list)
    rag_policy: Literal["not_used", "recommendation_explanation_only"] = "not_used"
    decision_source: Literal[
        "hard_rule",
        "rule_score",
        "rule_score_with_crisis_floor",
        "insufficient_data",
    ] = "rule_score"
    model_explanation: str = ""
    prompt_version: str = "risk-agent-rules-4.7.0"


class RiskAgent:
    """综合危机、情绪和趋势信号，输出可审计的风险等级和计算来源。"""

    name = "risk"
    version = "4.7.0"

    EMOTION_WEIGHTS = {
        "anxiety": 0.35,
        "stress": 0.35,
        "depression": 0.25,
        "loneliness": 0.05,
    }

    @classmethod
    def _emotion_risk(cls, emotion: EmotionAnalysis) -> tuple[float, RiskCalculationItem]:
        raw_score = (
            cls.EMOTION_WEIGHTS["anxiety"] * emotion.anxiety
            + cls.EMOTION_WEIGHTS["stress"] * emotion.stress
            + cls.EMOTION_WEIGHTS["depression"] * emotion.depression
            + cls.EMOTION_WEIGHTS["loneliness"] * emotion.loneliness
        )
        confidence_factor = max(0.2, emotion.confidence)
        score = min(1.0, raw_score * confidence_factor)
        trace = RiskCalculationItem(
            name="emotion_risk",
            formula=(
                "raw=(0.35*anxiety + 0.35*stress + 0.25*depression + "
                "0.05*loneliness); value=raw*max(0.2, emotion.confidence)"
            ),
            value=round(score, 4),
            weight=0.7,
            contribution=round(score * 0.7, 4),
            evidence=emotion.evidence[:5],
        )
        return score, trace

    @staticmethod
    def _trend_risk(trend: TrendAnalysis | None) -> tuple[float, RiskCalculationItem]:
        if trend is None:
            return 0.0, RiskCalculationItem(
                name="trend_risk",
                formula="no trend data => 0",
                value=0.0,
                weight=0.3,
                contribution=0.0,
                evidence=["没有传入趋势数据"],
            )

        score = 0.0
        worsening_count = 0
        for direction in (trend.stress_trend, trend.anxiety_trend, trend.depression_trend):
            if direction == "worsening":
                worsening_count += 1
                score += 0.2
        score += min(0.25, max(0.0, trend.stress_delta))
        score += min(0.15, max(0, trend.consecutive_rise) * 0.05)
        score = min(1.0, score)
        return score, RiskCalculationItem(
            name="trend_risk",
            formula=(
                "0.2*worsening_metric_count + min(0.25, stress_delta_positive) + "
                "min(0.15, consecutive_rise*0.05)"
            ),
            value=round(score, 4),
            weight=0.3,
            contribution=round(score * 0.3, 4),
            evidence=trend.evidence[:5],
        )

    @staticmethod
    def _confidence(
        crisis: CrisisAnalysis,
        emotion: EmotionAnalysis,
        trend: TrendAnalysis | None,
        evidence: list[str],
    ) -> float:
        base = 0.45
        base += 0.25 * crisis.confidence
        base += 0.2 * emotion.confidence
        if trend:
            base += 0.1 * trend.confidence
        if evidence:
            base += 0.05
        if getattr(emotion, "insufficient_data", False):
            base -= 0.2
        if crisis.validation_warnings or emotion.validation_warnings:
            base -= 0.1
        return max(0.0, min(1.0, round(base, 4)))

    @staticmethod
    def _level(score: float) -> Literal["low", "attention", "medium", "high"]:
        if score >= 0.85:
            return "high"
        if score >= 0.6:
            return "medium"
        if score >= 0.3:
            return "attention"
        return "low"

    @staticmethod
    def _recommendation(
        level: str,
        requires_human_review: bool,
        grounding: list[RiskRecommendationGrounding] | None = None,
    ) -> str:
        grounded_suffix = ""
        if grounding:
            first = grounding[0]
            grounded_suffix = f" 可参考本地知识库《{first.source}》/{first.chunk_id} 的相关建议。"
        if level == "high":
            return "建议立即联系身边可信任的人、学校心理中心或当地急救/危机服务，并优先确保当前安全。" + grounded_suffix
        if level == "medium":
            return "建议近期主动联系可信任的人或学校心理中心，持续观察风险变化。" + grounded_suffix
        if level == "attention":
            return "建议进行规律作息、压力调节和持续记录；如果状态加重，应主动寻求帮助。" + grounded_suffix
        if requires_human_review:
            return "当前信息不足但存在不确定信号，建议人工复核后再给出进一步建议。"
        return "保持当前支持和自我照顾，必要时继续寻求帮助。" + grounded_suffix

    @staticmethod
    def _unique_evidence(*groups: list[str]) -> list[str]:
        evidence: list[str] = []
        for group in groups:
            for item in group:
                if item and item not in evidence:
                    evidence.append(item)
        return evidence[:10]

    def assess(
        self,
        crisis: CrisisAnalysis,
        emotion: EmotionAnalysis,
        trend: TrendAnalysis | None = None,
        rag: RAGAnalysis | None = None,
    ) -> RiskAnalysis:
        grounding = self._rag_grounding(rag)
        rag_citations_used = [item.chunk_id for item in grounding]
        if crisis.level == "high" or crisis.action == "crisis_response" or crisis.hard_rule_triggered:
            evidence = self._unique_evidence(crisis.evidence)
            trace = [
                RiskCalculationItem(
                    name="crisis_hard_rule",
                    formula="crisis.level == high OR crisis.action == crisis_response OR hard_rule_triggered",
                    value=1.0,
                    weight=1.0,
                    contribution=1.0,
                    evidence=evidence,
                )
            ]
            return RiskAnalysis(
                risk_level="high",
                risk_score=1.0,
                confidence=max(0.9, crisis.confidence),
                emotion_risk=0.0,
                trend_risk=0.0,
                crisis_detected=True,
                evidence=evidence,
                main_factors=evidence,
                recommendation=self._recommendation("high", True, grounding),
                requires_human_review=True,
                hard_rule_applied=True,
                calculation_trace=trace,
                recommendation_grounding=grounding,
                rag_citations_used=rag_citations_used,
                rag_policy="recommendation_explanation_only" if grounding else "not_used",
                decision_source="hard_rule",
                model_explanation=self._model_explanation(
                    "高危危机规则优先，模型、情绪趋势或 RAG 都不能降低该风险等级。",
                    grounding,
                ),
            )

        emotion_risk, emotion_trace = self._emotion_risk(emotion)
        trend_risk, trend_trace = self._trend_risk(trend)
        risk_score = min(1.0, emotion_trace.contribution + trend_trace.contribution)
        decision_source: Literal[
            "hard_rule",
            "rule_score",
            "rule_score_with_crisis_floor",
            "insufficient_data",
        ] = "rule_score"

        if crisis.level == "medium" or crisis.action == "check_in":
            risk_score = max(risk_score, 0.6)
            decision_source = "rule_score_with_crisis_floor"

        if getattr(emotion, "insufficient_data", False) and crisis.level == "low" and trend is None:
            decision_source = "insufficient_data"

        level = self._level(risk_score)
        evidence = self._unique_evidence(emotion.evidence, trend.evidence if trend else [], crisis.evidence)
        requires_human_review = (
            crisis.requires_human_review
            or level in {"medium", "high"}
            or decision_source == "insufficient_data"
            or (crisis.level == "medium")
        )
        confidence = self._confidence(crisis, emotion, trend, evidence)
        if decision_source == "insufficient_data":
            confidence = min(confidence, 0.35)

        return RiskAnalysis(
            risk_level=level,
            risk_score=round(risk_score, 4),
            confidence=confidence,
            emotion_risk=round(emotion_risk, 4),
            trend_risk=round(trend_risk, 4),
            crisis_detected=crisis.level != "low" or crisis.self_harm or crisis.harm_to_others,
            evidence=evidence,
            main_factors=evidence,
            recommendation=self._recommendation(level, requires_human_review, grounding),
            requires_human_review=requires_human_review,
            hard_rule_applied=False,
            calculation_trace=[emotion_trace, trend_trace],
            recommendation_grounding=grounding,
            rag_citations_used=rag_citations_used,
            rag_policy="recommendation_explanation_only" if grounding else "not_used",
            decision_source=decision_source,
            model_explanation=self._model_explanation(
                "风险等级由硬规则、情绪风险和趋势风险共同决定；"
                "危机规则拥有最高优先级，模型结果和 RAG 资料不能覆盖安全规则。",
                grounding,
            ),
        )

    @staticmethod
    def _rag_grounding(rag: RAGAnalysis | None) -> list[RiskRecommendationGrounding]:
        if not rag or not rag.has_evidence:
            return []
        return [
            RiskRecommendationGrounding(
                source=citation.source,
                chunk_id=citation.chunk_id,
                category=citation.category,
                content_excerpt=citation.content[:220],
                score=citation.score,
            )
            for citation in rag.citations[:3]
        ]

    @staticmethod
    def _model_explanation(
        base: str,
        grounding: list[RiskRecommendationGrounding],
    ) -> str:
        if not grounding:
            return base + " 当前未使用 RAG 资料改变风险等级。"
        chunks = "、".join(f"{item.source}/{item.chunk_id}" for item in grounding)
        return base + f" RAG 仅用于建议解释和引用溯源，不能覆盖安全规则，不能降低风险等级；使用片段：{chunks}。"
