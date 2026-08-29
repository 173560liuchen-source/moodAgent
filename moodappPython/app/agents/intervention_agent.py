from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .crisis_agent import CrisisAnalysis
from .emotion_agent import EmotionAnalysis
from .profile_agent import ProfileAnalysis
from .rag_agent import RAGAnalysis
from .risk_agent import RiskAnalysis
from .trend_agent import TrendAnalysis


InterventionLevel = Literal["low", "attention", "medium", "high"]


class InterventionRAGGrounding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    content_excerpt: str = Field(min_length=1, max_length=240)
    score: float = Field(ge=0.0, le=1.0)


class InterventionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int = Field(ge=1, le=10)
    # 在同一份干预计划内保持稳定，用于接收“这一个行动”的反馈。
    # 与 Java 端的 plan_id 组合后，构成动作级反馈的唯一定位。
    action_id: str = Field(default="", max_length=40)
    action_type: Literal[
        "self_regulation",
        "knowledge_recommendation",
        "active_check_in",
        "social_support",
        "school_center",
        "crisis_response",
        "human_review",
    ]
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=500)
    related_profile_categories: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def assign_action_id(self) -> "InterventionAction":
        if not self.action_id:
            self.action_id = f"action-{self.priority}"
        return self


class InterventionAnalysis(BaseModel):
    """干预决策输出。

    用于 Java 端展示和持久化。Python 只生成策略，不直接通知任何人。
    """

    model_config = ConfigDict(extra="forbid")

    agent: str = "intervention"
    intervention_level: InterventionLevel
    risk_level_source: str = Field(min_length=1)
    strategy: str = Field(min_length=1, max_length=500)
    actions: list[InterventionAction] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    safety_constraints: list[str] = Field(default_factory=list)
    profile_used: list[str] = Field(default_factory=list)
    rag_citations_used: list[str] = Field(default_factory=list)
    rag_grounding: list[InterventionRAGGrounding] = Field(default_factory=list)
    requires_human_review: bool = False
    prohibited_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    prompt_version: str = "intervention-agent-rules-6.5.0"


class InterventionAgent:
    """画像驱动的干预决策智能体。

    原则：
    - 高危必须优先安全响应和人工介入；
    - 中风险必须建议可信任的人或学校心理中心；
    - attention 强调持续观察和主动沟通；
    - low 才允许以自我调节和知识推荐为主；
    - 不生成医疗诊断，不承诺治疗效果。
    """

    name = "intervention"
    version = "6.7.0"

    def plan(
        self,
        *,
        crisis: CrisisAnalysis,
        emotion: EmotionAnalysis | None = None,
        trend: TrendAnalysis | None = None,
        risk: RiskAnalysis | None = None,
        profile: ProfileAnalysis | None = None,
        rag: RAGAnalysis | None = None,
    ) -> InterventionAnalysis:
        level, source = self._resolve_level(crisis=crisis, emotion=emotion, trend=trend, risk=risk)
        profile_items = profile.patch_items if profile else []
        profile_categories = sorted({item.category for item in profile_items})
        evidence = self._collect_evidence(crisis=crisis, emotion=emotion, trend=trend, risk=risk, profile=profile, rag=rag)
        rag_citations_used = [citation.chunk_id for citation in (rag.citations if rag and rag.has_evidence else [])[:3]]
        rag_grounding = self._rag_grounding(rag)

        if level == "high":
            return self._high_plan(crisis, source, profile_categories, evidence, rag_citations_used, rag_grounding)
        if level == "medium":
            return self._medium_plan(crisis, source, profile_categories, evidence, rag_citations_used, rag_grounding)
        if level == "attention":
            return self._attention_plan(source, profile_categories, evidence, rag_citations_used, rag_grounding)
        return self._low_plan(source, profile_categories, evidence, rag_citations_used, rag_grounding)

    @staticmethod
    def _resolve_level(
        *,
        crisis: CrisisAnalysis,
        emotion: EmotionAnalysis | None,
        trend: TrendAnalysis | None,
        risk: RiskAnalysis | None,
    ) -> tuple[InterventionLevel, str]:
        if crisis.level == "high" or crisis.action == "crisis_response":
            return "high", "crisis_agent"
        if risk and risk.risk_level == "high":
            return "high", "risk_agent"
        if crisis.level == "medium" or crisis.action == "check_in":
            return "medium", "crisis_agent"
        if risk and risk.risk_level == "medium":
            return "medium", "risk_agent"
        if risk and risk.risk_level in {"attention", "low"}:
            if risk.risk_level == "attention":
                return "attention", "risk_agent"
        if trend and (
            trend.stress_trend == "worsening"
            or trend.anxiety_trend == "worsening"
            or trend.depression_trend == "worsening"
            or trend.consecutive_rise >= 2
        ):
            return "attention", "trend_agent"
        if emotion and not emotion.insufficient_data:
            high_emotion = max(emotion.stress, emotion.anxiety, emotion.depression)
            if high_emotion >= 0.75 and emotion.confidence >= 0.45:
                return "attention", "emotion_agent"
        return "low", "default"

    def _low_plan(
        self,
        source: str,
        profile_categories: list[str],
        evidence: list[str],
        rag_citations_used: list[str],
        rag_grounding: list[InterventionRAGGrounding],
    ) -> InterventionAnalysis:
        actions = [
            InterventionAction(
                priority=1,
                action_type="self_regulation",
                title="低负担自我调节",
                description=self._personalized_self_regulation(profile_categories),
                rationale="当前未检测到中高危信号，可优先使用低负担自我调节。",
                related_profile_categories=self._related(profile_categories, {"sleep_status", "study_status", "coping_method"}),
                evidence=evidence[:3],
            ),
            InterventionAction(
                priority=2,
                action_type="knowledge_recommendation",
                title="知识库支持建议",
                description=self._knowledge_description(
                    rag_grounding,
                    fallback="结合本地知识库资料，选择一条最容易执行的压力或睡眠管理建议。",
                ),
                rationale=self._knowledge_rationale(rag_grounding),
                related_profile_categories=self._related(profile_categories, {"effective_advice", "study_status", "sleep_status"}),
                evidence=self._rag_evidence(rag_grounding) or rag_citations_used,
            ),
        ]
        return InterventionAnalysis(
            intervention_level="low",
            risk_level_source=source,
            strategy="以自我调节和知识推荐为主，继续观察用户状态变化。",
            actions=actions,
            rationale=evidence or ["当前无明确危机信号。"],
            safety_constraints=["不做医疗诊断", "不承诺治疗效果", "如风险升高需转入人工/线下支持"],
            profile_used=profile_categories,
            rag_citations_used=rag_citations_used,
            rag_grounding=rag_grounding,
            requires_human_review=False,
            prohibited_actions=["不得制造恐慌", "不得将普通压力描述为疾病诊断"],
            confidence=0.72,
        )

    def _attention_plan(
        self,
        source: str,
        profile_categories: list[str],
        evidence: list[str],
        rag_citations_used: list[str],
        rag_grounding: list[InterventionRAGGrounding],
    ) -> InterventionAnalysis:
        actions = [
            InterventionAction(
                priority=1,
                action_type="active_check_in",
                title="持续观察和主动沟通",
                description=self._knowledge_description(
                    rag_grounding,
                    fallback="建议后续继续追踪睡眠、学习压力和情绪波动，并主动询问是否有加重迹象。",
                ),
                rationale="已出现持续压力、趋势上升或明显情绪强度，需要比低风险更主动的支持；若有 RAG 引用，则优先采用可溯源建议。",
                related_profile_categories=self._related(profile_categories, {"sleep_status", "study_status", "stress_source"}),
                evidence=(evidence[:4] + self._rag_evidence(rag_grounding))[:6],
            ),
            InterventionAction(
                priority=2,
                action_type="social_support",
                title="连接可信任支持",
                description="如果用户愿意，可鼓励其告诉一位可信任的人，例如朋友、家人、老师或辅导员。",
                rationale="attention 等级需要提前建立支持资源，避免风险进一步升高。",
                related_profile_categories=self._related(profile_categories, {"support_resource", "social_status"}),
                evidence=evidence[:3],
            ),
        ]
        return InterventionAnalysis(
            intervention_level="attention",
            risk_level_source=source,
            strategy="以持续观察、主动沟通和支持资源连接为主。",
            actions=actions,
            rationale=evidence or ["检测到需要持续观察的情绪或趋势信号。"],
            safety_constraints=["不做医疗诊断", "不承诺治疗效果", "若出现自伤/他伤信号立即升级"],
            profile_used=profile_categories,
            rag_citations_used=rag_citations_used,
            rag_grounding=rag_grounding,
            requires_human_review=False,
            prohibited_actions=["不得只给泛泛鸡汤", "不得忽略风险升级可能性"],
            confidence=0.78,
        )

    def _medium_plan(
        self,
        crisis: CrisisAnalysis,
        source: str,
        profile_categories: list[str],
        evidence: list[str],
        rag_citations_used: list[str],
        rag_grounding: list[InterventionRAGGrounding],
    ) -> InterventionAnalysis:
        actions = [
            InterventionAction(
                priority=1,
                action_type="social_support",
                title="联系可信任的人",
                description="建议用户今天联系一位可信任的人，说明自己近期状态不太好，不要独自硬撑。",
                rationale="中风险需要现实支持资源介入，不能只依赖自我调节。",
                related_profile_categories=self._related(profile_categories, {"support_resource", "social_status"}),
                evidence=evidence[:4],
            ),
            InterventionAction(
                priority=2,
                action_type="school_center",
                title="联系学校心理中心",
                description=self._school_center_description(rag_grounding),
                rationale="中风险需要专业或学校支持渠道介入；若本地知识库提供学校资源或危机规范，应优先展示可溯源信息。",
                related_profile_categories=self._related(profile_categories, {"support_resource", "stress_source"}),
                evidence=(crisis.evidence[:3] or evidence[:3]) + self._rag_evidence(rag_grounding),
            ),
        ]
        return InterventionAnalysis(
            intervention_level="medium",
            risk_level_source=source,
            strategy="建议联系可信任的人或学校心理中心，并持续观察风险变化。",
            actions=actions,
            rationale=evidence or ["CrisisAgent 或 RiskAgent 判断为中风险。"],
            safety_constraints=["不以普通自我调节替代求助", "不做医疗诊断", "不承诺治疗效果"],
            profile_used=profile_categories,
            rag_citations_used=rag_citations_used,
            rag_grounding=rag_grounding,
            requires_human_review=True,
            prohibited_actions=["不得只推荐深呼吸/听歌", "不得弱化中风险", "不得建议用户独自承受"],
            confidence=max(0.82, crisis.confidence),
        )

    def _high_plan(
        self,
        crisis: CrisisAnalysis,
        source: str,
        profile_categories: list[str],
        evidence: list[str],
        rag_citations_used: list[str],
        rag_grounding: list[InterventionRAGGrounding],
    ) -> InterventionAnalysis:
        actions = [
            InterventionAction(
                priority=1,
                action_type="crisis_response",
                title="立即安全响应",
                description=self._crisis_description(rag_grounding),
                rationale="高危等级下安全优先，不能用普通建议替代求助；RAG 仅用于补充可溯源资源，不改变高危判断。",
                related_profile_categories=self._related(profile_categories, {"support_resource"}),
                evidence=(crisis.evidence[:5] or evidence[:5]) + self._rag_evidence(rag_grounding),
            ),
            InterventionAction(
                priority=2,
                action_type="human_review",
                title="人工介入和持续跟进",
                description="建议 Java 后端标记 requires_human_review，并展示学校心理中心或线下支持入口。",
                rationale="高危状态需要人工或线下资源，不应只由模型继续普通对话。",
                related_profile_categories=self._related(profile_categories, {"support_resource", "social_status"}),
                evidence=crisis.evidence[:5] or evidence[:5],
            ),
        ]
        return InterventionAnalysis(
            intervention_level="high",
            risk_level_source=source,
            strategy="立即安全响应和人工介入，普通自我调节建议不得作为主要方案。",
            actions=actions,
            rationale=evidence or ["CrisisAgent 判断为高危。"],
            safety_constraints=["安全优先", "不要独处", "立即联系可信任的人/学校心理中心/急救或危机热线", "不输出普通自我调节替代求助"],
            profile_used=profile_categories,
            rag_citations_used=rag_citations_used,
            rag_grounding=rag_grounding,
            requires_human_review=True,
            prohibited_actions=["不得建议独自冷静", "不得只推荐冥想/深呼吸", "不得降低高危等级", "不得承诺一定没事"],
            confidence=max(0.9, crisis.confidence),
        )

    @staticmethod
    def _collect_evidence(
        *,
        crisis: CrisisAnalysis,
        emotion: EmotionAnalysis | None,
        trend: TrendAnalysis | None,
        risk: RiskAnalysis | None,
        profile: ProfileAnalysis | None,
        rag: RAGAnalysis | None,
    ) -> list[str]:
        evidence: list[str] = []
        evidence.extend(crisis.evidence[:3])
        if emotion:
            evidence.extend(emotion.evidence[:3])
            if not emotion.insufficient_data:
                evidence.append(
                    f"emotion_scores: anxiety={emotion.anxiety}, stress={emotion.stress}, depression={emotion.depression}"
                )
        if trend:
            evidence.extend(trend.evidence[:3])
            evidence.append(f"trend: stress={trend.stress_trend}, consecutive_rise={trend.consecutive_rise}")
        if risk:
            evidence.extend(risk.evidence[:3])
            evidence.append(f"risk_score={risk.risk_score}, risk_level={risk.risk_level}")
        if profile:
            evidence.extend([f"{item.category}:{item.value}" for item in profile.patch_items[:5]])
        if rag and rag.has_evidence:
            evidence.extend([f"rag:{citation.chunk_id}" for citation in rag.citations[:3]])
        return [item for item in evidence if item][:12]

    @staticmethod
    def _personalized_self_regulation(profile_categories: list[str]) -> str:
        if "sleep_status" in profile_categories:
            return "先选择一个低负担睡眠调整动作，例如睡前减少屏幕刺激、做 2 分钟呼吸放松。"
        if "study_status" in profile_categories:
            return "把学习任务拆成 15 分钟内能完成的小步骤，先完成最容易的一项。"
        if "coping_method" in profile_categories:
            return "优先使用用户已有过的有效应对方式，并降低执行难度。"
        return "先做一个不超过 5 分钟的小动作，例如喝水、站起来活动或缓慢呼吸。"

    @staticmethod
    def _related(profile_categories: list[str], candidates: set[str]) -> list[str]:
        return [category for category in profile_categories if category in candidates]

    @staticmethod
    def _rag_grounding(rag: RAGAnalysis | None) -> list[InterventionRAGGrounding]:
        if not rag or not rag.has_evidence:
            return []
        return [
            InterventionRAGGrounding(
                source=citation.source,
                chunk_id=citation.chunk_id,
                category=citation.category,
                content_excerpt=citation.content[:220],
                score=citation.score,
            )
            for citation in rag.citations[:3]
        ]

    @staticmethod
    def _rag_evidence(grounding: list[InterventionRAGGrounding]) -> list[str]:
        return [
            f"{item.source}/{item.chunk_id}: {item.content_excerpt[:80]}"
            for item in grounding
        ]

    @staticmethod
    def _knowledge_description(
        grounding: list[InterventionRAGGrounding],
        *,
        fallback: str,
    ) -> str:
        if not grounding:
            return fallback
        first = grounding[0]
        return (
            f"依据本地知识库《{first.source}》/{first.chunk_id}，可优先选择一个低负担、"
            f"可立即执行的建议：{first.content_excerpt[:160]}"
        )

    @staticmethod
    def _knowledge_rationale(grounding: list[InterventionRAGGrounding]) -> str:
        if not grounding:
            return "RAG 未返回可引用资料，本建议仅基于风险等级和画像规则生成。"
        return "该建议来自本地知识库真实检索片段，保留 source/chunk_id，便于 Java 端展示引用来源。"

    @staticmethod
    def _school_center_description(grounding: list[InterventionRAGGrounding]) -> str:
        resource = next(
            (item for item in grounding if item.category in {"school_resources", "crisis_guidelines"}),
            None,
        )
        if resource:
            return f"建议联系学校心理中心或辅导员，并参考《{resource.source}》/{resource.chunk_id}：{resource.content_excerpt[:160]}"
        return "建议预约学校心理中心或联系辅导员，获得线下支持和持续跟进。"

    @staticmethod
    def _crisis_description(grounding: list[InterventionRAGGrounding]) -> str:
        resource = next(
            (item for item in grounding if item.category in {"crisis_guidelines", "school_resources"}),
            None,
        )
        if resource:
            return (
                f"请用户尽量不要独处，立即联系身边可信任的人；如有即时危险，联系当地急救服务或危机热线。"
                f"可展示《{resource.source}》/{resource.chunk_id} 作为可溯源安全资源。"
            )
        return "请用户尽量不要独处，立即联系身边可信任的人；如有即时危险，联系当地急救服务或危机热线。"
