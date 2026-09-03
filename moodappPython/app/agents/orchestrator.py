from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Literal, TypedDict

try:
    from langgraph.graph import END, StateGraph as LangGraphStateGraph
except ImportError as exc:  # pragma: no cover - exercised in dependency checks.
    END = "__end__"
    LangGraphStateGraph = None  # type: ignore[assignment]
    _LANGGRAPH_IMPORT_ERROR: ImportError | None = exc
else:
    _LANGGRAPH_IMPORT_ERROR = None

from ..core.contracts import AgentContext, AgentTraceEvent
from ..config import RAG_INTENT_TIMEOUT_SECONDS
from ..ablation import AblationConfig, active_ablation
from ..model_gateway import ModelGateway, ModelGatewayError
from ..schemas import ChatMessage, ModelChatRequest, ModelChatResponse, OrchestrationRequest
from .audit_agent import AuditAnalysis
from .crisis_agent import CRISIS_RESPONSE_TEMPLATES, CrisisAgent, CrisisAnalysis
from .emotion_agent import EmotionAnalysis
from .evaluator_agent import EvaluationAnalysis
from .follow_up_agent import FollowUpAnalysis
from .intervention_agent import InterventionAction, InterventionAnalysis
from .profile_agent import ProfileAnalysis, ProfilePatchItem
from .rag_agent import RAGAnalysis
from .registry import AgentRegistry, build_default_registry
from .risk_agent import RiskAnalysis, RiskCalculationItem
from .risk_constrained_router import (
    RiskConstrainedRouter,
    RoutingInput,
)
from .safety_gate import SafetyDecision
from .trend_agent import EmotionPoint, TrendAnalysis


WorkflowNodeName = Literal[
    "safety_gate",
    "initial_analysis",
    "risk_assessment",
    "follow_up_assessment",
    "profile_update",
    "intervention_plan",
    "dialogue",
    "evaluator",
    "audit",
    "blocked",
    "crisis_response",
]
RAGIntent = Literal["retrieve", "conversation", "uncertain"]
RouteName = Literal[
    "exploratory_support",
    "knowledge_support",
    "structured_assessment",
    "follow_up_support",
    "crisis_response",
]

_STREAM_CALLBACK: ContextVar[Callable[[str], Awaitable[None]] | None] = ContextVar(
    "orchestrator_stream_callback", default=None
)


class OrchestratorWorkflowState(TypedDict):
    """LangGraph 工作流状态。

    只保存本次请求内的短生命周期状态，不保存完整用户历史到 Python 侧。
    """

    request: OrchestrationRequest
    context: AgentContext
    status: str
    trace: list[str]
    values: dict[str, Any]
    trace_events: list[AgentTraceEvent]


class RouteDecision(TypedDict):
    """本轮处理路径；首轮不产生完整风险分级。"""

    route: RouteName
    reasons: list[str]
    evidence_sufficient: bool
    rag_needed: bool
    features: dict[str, Any]
    route_scores: dict[str, float]
    hard_constraint_triggered: bool
    policy_version: str


class OrchestrationResult:
    def __init__(
        self,
        reply: str,
        crisis: CrisisAnalysis,
        emotion: EmotionAnalysis | None,
        trace: list[str],
        model: str,
        request_id: str,
        trace_events: list[AgentTraceEvent],
        safety: SafetyDecision,
        rag: RAGAnalysis | None = None,
        trend: TrendAnalysis | None = None,
        risk: RiskAnalysis | None = None,
        profile: ProfileAnalysis | None = None,
        intervention: InterventionAnalysis | None = None,
        follow_up: FollowUpAnalysis | None = None,
        evaluator: EvaluationAnalysis | None = None,
        audit: AuditAnalysis | None = None,
    ) -> None:
        self.reply = reply
        self.crisis = crisis
        self.emotion = emotion
        self.rag = rag
        self.trend = trend
        self.risk = risk
        self.profile = profile
        self.intervention = intervention
        self.follow_up = follow_up
        self.evaluator = evaluator
        self.audit = audit
        self.trace = trace
        self.model = model
        self.request_id = request_id
        self.trace_events = trace_events
        self.safety = safety


class LangGraphDependencyError(RuntimeError):
    pass


class Orchestrator:
    """基于 LangGraph 的安全优先多智能体编排器。

    设计原则：
    1. SafetyGate 永远是入口节点；
    2. 高危路径由规则/危机节点直接进入 crisis_response；
    3. 普通路径并发执行危机、情绪、RAG 和趋势分析，再计算综合风险；
    4. DialogueAgent 在风险、画像和干预方案完成后生成回复；
    5. 对外返回结构保持与旧 Orchestrator 兼容。
    """

    workflow_engine = "langgraph"
    workflow_version = "7.3.0"

    RAG_KNOWLEDGE_REQUEST_TERMS = (
        "怎么办", "怎么做", "如何", "建议", "方法", "技巧", "缓解", "改善",
        "推荐", "资料", "依据", "为什么", "是什么", "有没有", "哪些",
        "可以吗", "能不能", "会不会", "是否", "怎样", "应对",
        "准备什么", "还能", "哪里可以", "去哪里", "怎么预约", "专业帮助",
    )
    RAG_DOMAIN_TERMS = (
        "压力", "焦虑", "紧张", "孤独", "低落", "难过", "沮丧", "疲惫",
        "崩溃", "没人理解", "没朋友", "学校", "大学", "高中", "宿舍",
        "家庭", "父母", "考试", "考研", "论文", "作业", "绩点", "实习",
        "就业", "睡眠", "失眠", "睡不着", "睡不好", "早醒", "夜醒", "熬夜", "补觉", "作息",
        "量表", "sas", "sds", "思维模式", "自我评价", "心理测评", "心理咨询", "校医院",
    )
    RAG_SUPPORT_RESOURCE_TERMS = (
        "心理中心", "心理老师", "辅导员", "校医院", "热线", "预约咨询",
        "校内支持", "求助资源", "危机热线",
    )
    RAG_CRISIS_TERMS = (
        "自伤", "自残", "自杀", "轻生", "不想活", "伤害自己", "伤害他人",
        "伤人", "撑不住",
    )
    # “我是不是得了某种心理疾病”不是普通闲聊，也不能由生成模型直接下诊断。
    # 这类问题必须先检索可信资料，再由回复环节说明筛查与诊断边界。
    RAG_DIAGNOSIS_TERMS = (
        "抑郁症", "焦虑症", "双相情感障碍", "躁郁症", "强迫症",
        "创伤后应激障碍", "精神疾病", "心理疾病",
    )
    RAG_DIAGNOSIS_REQUEST_TERMS = (
        "我是不是", "我是否", "我有没有", "是不是已经得了", "是不是得了",
        "给我诊断", "帮我诊断", "直接诊断", "能不能诊断", "能否诊断",
        "给我确诊", "帮我确诊", "能不能确诊", "能否确诊",
        "判断我是不是", "告诉我是不是",
    )
    RAG_NON_DOMAIN_TERMS = (
        "天气", "彩票", "股票", "发动机", "机油", "量子", "路由器", "手机处理器",
        "红烧肉", "冰糖", "旅游签证", "房贷", "端口转发",
    )
    FOLLOW_UP_TERMS = (
        "做了", "试了", "没有改善", "没效果", "好一点", "加重了",
        "上次", "之前的建议", "干预", "计划", "刚才的方法", "刚才的建议",
        "帮我调整", "调整成", "改成", "减少到", "缩减为", "换成",
        "只做一个", "保留这个", "继续这个方案",
    )
    ASSESSMENT_DURATION_TERMS = (
        "一周", "两周", "半个月", "一个月", "很久", "持续", "一直",
    )
    ASSESSMENT_DETERIORATION_TERMS = (
        "越来越", "加重", "恶化", "更严重", "一天比一天", "反复出现",
    )
    ASSESSMENT_FUNCTION_IMPACT_TERMS = (
        "影响上课", "影响学习", "影响生活", "不想上课", "无法上课",
        "不能上课", "不能正常", "维持不了", "无法维持", "吃不下",
        "无法完成", "做不了",
    )

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or build_default_registry(ModelGateway())
        self.crisis_agent: CrisisAgent = self.registry.create("crisis")
        self.chat_agent = self.registry.create("chat")
        self.emotion_agent = self.registry.create("emotion")
        self.rag_agent = self.registry.create("rag")
        self.trend_agent = self.registry.create("trend")
        self.risk_agent = self.registry.create("risk")
        self.profile_agent = self.registry.create("profile")
        self.intervention_agent = self.registry.create("intervention")
        self.follow_up_agent = self.registry.create("follow_up")
        self.evaluator_agent = self.registry.create("evaluator")
        self.audit_agent = self.registry.create("audit")
        self.safety_gate = self.registry.create("safety_gate")
        self.risk_router = RiskConstrainedRouter()    # 风险约束路由器
        self._workflow: Any | None = None             # 工作流（延迟构建）

    async def run(self, request: OrchestrationRequest) -> OrchestrationResult:
        workflow = self._get_workflow()
        initial_state = self._initial_state(request)
        state: OrchestratorWorkflowState = await workflow.ainvoke(initial_state)
        state["status"] = "completed"

        values = state["values"]
        safety = values["safety"]
        crisis = values["crisis"]
        chat_result = values.get("chat")
        return OrchestrationResult(
            reply=values.get("reply", chat_result.content if chat_result else ""),
            crisis=crisis,
            emotion=values.get("emotion"),
            trace=state["trace"],
            model=values.get("model", chat_result.model if chat_result else ""),
            request_id=request.context.request_id,
            trace_events=state["trace_events"],
            safety=safety,
            rag=values.get("rag"),
            trend=values.get("trend"),
            risk=values.get("risk"),
            profile=values.get("profile"),
            intervention=values.get("intervention"),
            follow_up=values.get("follow_up"),
            evaluator=values.get("evaluator"),
            audit=values.get("audit"),
        )

    async def run_stream(
        self,
        request: OrchestrationRequest,
        on_chunk: Callable[[str], Awaitable[None]],
    ) -> OrchestrationResult:
        token = _STREAM_CALLBACK.set(on_chunk)
        try:
            return await self.run(request)
        finally:
            _STREAM_CALLBACK.reset(token)

    @staticmethod
    def _initial_state(request: OrchestrationRequest) -> OrchestratorWorkflowState:
        return {
            "request": request,
            "context": request.context,
            "status": "running",
            "trace": [],
            "values": {},
            "trace_events": [],
        }

    def _get_workflow(self) -> Any:
        if self._workflow is not None:
            return self._workflow
        if LangGraphStateGraph is None:
            raise LangGraphDependencyError(
                "LangGraph 未安装。请在 D:\\protect\\moodappPython 中执行："
                "pip install -r requirements.txt"
            ) from _LANGGRAPH_IMPORT_ERROR
        self._workflow = self._build_workflow()
        return self._workflow

    @classmethod
    def _rule_based_rag_intent(cls, message: str) -> RAGIntent:
        clean = (message or "").strip().lower()
        if not clean:
            return "conversation"
        if any(term in clean for term in cls.RAG_NON_DOMAIN_TERMS):
            return "conversation"
        explicit_request = any(term in clean for term in cls.RAG_KNOWLEDGE_REQUEST_TERMS)
        domain_signal = any(term in clean for term in cls.RAG_DOMAIN_TERMS)
        critical_resource = any(term in clean for term in cls.RAG_SUPPORT_RESOURCE_TERMS)
        crisis_signal = any(term in clean for term in cls.RAG_CRISIS_TERMS)
        diagnosis_signal = any(term in clean for term in cls.RAG_DIAGNOSIS_TERMS)
        diagnosis_request = (
            diagnosis_signal
            and any(term in clean for term in cls.RAG_DIAGNOSIS_REQUEST_TERMS)
        )
        looks_like_question = (
            "？" in clean
            or "?" in clean
            or any(term in clean for term in (
                "怎么", "如何", "为什么", "有没有", "可以吗", "能不能", "会不会", "是否",
                "哪里", "哪些", "怎样", "应对", "准备什么", "还能",
            ))
        )
        if diagnosis_signal and not diagnosis_request and not explicit_request and not looks_like_question:
            return "conversation"
        if (
            diagnosis_request
            or critical_resource
            or crisis_signal
            or explicit_request
            or (domain_signal and looks_like_question)
        ):
            return "retrieve"
        if domain_signal:
            return "conversation"
        return "uncertain"

    async def _classify_rag_intent(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
    ) -> Literal["retrieve", "conversation"]:
        recent_user_context = [
            item.content for item in (history or []) if item.role == "user"
        ][-2:]
        context = "\n".join(recent_user_context + [message])[-800:]
        request = ModelChatRequest(
            messages=[
                ChatMessage(
                    role="system",
                    content=(
                        "判断用户是否需要检索心理知识库。"
                        "询问方法、知识、原因、资料、学校资源、求助渠道或危机帮助时返回 retrieve；"
                        "只是在表达情绪、倾诉或希望陪伴时返回 conversation。"
                        "只能返回 retrieve 或 conversation。"
                    ),
                ),
                ChatMessage(role="user", content=context),
            ],
            temperature=0.0,
            max_tokens=4,
        )
        response = await asyncio.wait_for(
            self.chat_agent.gateway.chat(request),
            timeout=RAG_INTENT_TIMEOUT_SECONDS,
        )
        intent = response.content.strip().lower()
        return "retrieve" if intent == "retrieve" else "conversation"

    async def _should_retrieve_knowledge(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
    ) -> bool:
        intent = self._rule_based_rag_intent(message)
        if intent == "retrieve":
            return True
        if intent == "conversation":
            return False
        try:
            return await self._classify_rag_intent(message, history) == "retrieve"
        except (asyncio.TimeoutError, ModelGatewayError):
            return False

    @classmethod
    def _has_follow_up_context(cls, request: OrchestrationRequest) -> bool:
        """只有已有方案且本轮明确反馈或调整方案时，才走跟进链路。"""
        metadata = request.context.metadata or {}
        has_prior_plan = bool(
            metadata.get("latest_intervention")
            or metadata.get("intervention_plan")
        )
        message = request.message.lower()
        # action_feedbacks 会随用户画像长期存在，不能仅因历史列表非空就把
        # 后续所有新话题都识别成跟进。路由必须由当前轮文本明确指向已有方案。
        return has_prior_plan and any(term in message for term in cls.FOLLOW_UP_TERMS)

    @staticmethod
    def _requires_attention(value: Any) -> bool:
        if isinstance(value, dict):
            value = value.get("risk_level") or value.get("level") or value.get("severity")
        normalized = str(value or "").strip().lower()
        return normalized in {
            "medium", "high", "critical", "moderate", "severe",
            "需关注", "中风险", "高风险", "中度", "重度",
        }

    @classmethod
    def _has_assessment_evidence(cls, request: OrchestrationRequest) -> bool:
        """仅用恶化、功能受损或明确关注状态作为综合评估证据。"""
        metadata = request.context.metadata or {}
        message = request.message.lower()
        has_duration = any(term in message for term in cls.ASSESSMENT_DURATION_TERMS)
        has_deterioration = any(term in message for term in cls.ASSESSMENT_DETERIORATION_TERMS)
        has_function_impact = any(term in message for term in cls.ASSESSMENT_FUNCTION_IMPACT_TERMS)

        points = cls._trend_points(metadata)
        trend_worsening = False
        sustained_high = False
        if len(points) >= 2:
            first = points[0]
            last = points[-1]
            worsening_delta = max(
                last.anxiety - first.anxiety,
                last.stress - first.stress,
                last.depression - first.depression,
            )
            last_load = max(last.anxiety, last.stress, last.depression)
            previous_load = max(points[-2].anxiety, points[-2].stress, points[-2].depression)
            trend_worsening = worsening_delta >= 0.15 and last_load >= 0.55
            sustained_high = last_load >= 0.75 and previous_load >= 0.65

        has_assessment = cls._requires_attention(
            metadata.get("assessment_result") or metadata.get("assessment")
        )
        has_prior_attention = cls._requires_attention(
            metadata.get("crisis_state") or metadata.get("previous_risk_state")
        )
        explicit_longitudinal_impact = has_function_impact and (has_duration or has_deterioration)
        return bool(
            explicit_longitudinal_impact
            or trend_worsening
            or sustained_high
            or has_assessment
            or has_prior_attention
        )

    @staticmethod
    def _emotion_load(emotion: EmotionAnalysis | None) -> float:
        if emotion is None:
            return 0.0
        return max(emotion.anxiety, emotion.stress, emotion.depression, emotion.loneliness)

    @classmethod
    def _trend_load(cls, request: OrchestrationRequest) -> float:
        metadata = request.context.metadata or {}
        points = cls._trend_points(metadata)
        if points:
            last = points[-1]
            end_load = max(last.anxiety, last.stress, last.depression)
            if len(points) >= 2:
                first = points[0]
                worsening_delta = max(
                    last.anxiety - first.anxiety,
                    last.stress - first.stress,
                    last.depression - first.depression,
                )
                if worsening_delta >= 0.10:
                    return round(min(1.0, max(end_load, 0.5 + worsening_delta)), 4)
                previous = points[-2]
                previous_load = max(previous.anxiety, previous.stress, previous.depression)
                if end_load >= 0.75 and previous_load >= 0.65:
                    return round(end_load, 4)
            # 单点或稳定的轻度历史只提供背景，不构成高趋势负荷。
            return round(end_load * 0.5, 4)
        if metadata.get("assessment") or metadata.get("assessment_result"):
            return 0.5
        return 0.0

    def _legacy_decide_route(
        self,
        request: OrchestrationRequest,
        *,
        rag_needed: bool,
    ) -> RouteDecision:
        """Legacy policy, retained only for offline router ablation."""
        if self._has_follow_up_context(request):
            return {
                "route": "follow_up_support",
                "reasons": ["检测到已有干预/关注状态及本轮反馈"],
                "evidence_sufficient": True,
                "rag_needed": rag_needed,
                "features": {}, "route_scores": {}, "hard_constraint_triggered": False,
                "policy_version": "legacy-route-rules-7.2.0",
            }
        if self._has_assessment_evidence(request):
            return {
                "route": "structured_assessment",
                "reasons": ["已有多轮表达、趋势、测评或历史关注证据"],
                "evidence_sufficient": True,
                "rag_needed": rag_needed,
                "features": {}, "route_scores": {}, "hard_constraint_triggered": False,
                "policy_version": "legacy-route-rules-7.2.0",
            }
        if rag_needed:
            return {
                "route": "knowledge_support",
                "reasons": ["用户明确需要方法、知识或求助资源"],
                "evidence_sufficient": False,
                "rag_needed": True,
                "features": {}, "route_scores": {}, "hard_constraint_triggered": False,
                "policy_version": "legacy-route-rules-7.2.0",
            }
        return {
            "route": "exploratory_support",
            "reasons": ["当前证据不足，仅进行探索式支持，不形成综合风险分级"],
            "evidence_sufficient": False,
            "rag_needed": False,
            "features": {}, "route_scores": {}, "hard_constraint_triggered": False,
            "policy_version": "legacy-route-rules-7.2.0",
        }

    async def _decide_route(
        self,
        request: OrchestrationRequest,
        *,
        rag_needed: bool,
        crisis: CrisisAnalysis | None = None,
        emotion: EmotionAnalysis | None = None,
    ) -> RouteDecision:
        if not self._ablation(request).enable_risk_router:
            return self._legacy_decide_route(request, rag_needed=rag_needed)
        safety = RoutingInput(
            crisis_level=crisis.level if crisis else "low",
            crisis_action=crisis.action if crisis else "normal_support",
            emotion_load=self._emotion_load(emotion),
            trend_load=self._trend_load(request),
            knowledge_need=1.0 if rag_needed else 0.0,
            follow_up_need=1.0 if self._has_follow_up_context(request) else 0.0,
            assessment_evidence=self._has_assessment_evidence(request),
            user_turn_count=sum(1 for item in request.history if item.role == "user"),
        )
        return self.risk_router.decide(safety).model_dump()

    def _build_workflow(self) -> Any:
        graph = LangGraphStateGraph(OrchestratorWorkflowState)
        graph.add_node("safety_gate", self._safety_node)
        graph.add_node("initial_analysis", self._initial_analysis_node)
        graph.add_node("risk_assessment", self._risk_assessment_node)
        graph.add_node("follow_up_assessment", self._follow_up_assessment_node)
        graph.add_node("profile_update", self._profile_update_node)
        graph.add_node("intervention_plan", self._intervention_plan_node)
        graph.add_node("dialogue", self._dialogue_node)
        graph.add_node("evaluator", self._evaluator_node)
        graph.add_node("audit", self._audit_node)
        graph.add_node("blocked", self._blocked_node)
        graph.add_node("crisis_response", self._crisis_response_node)

        graph.set_entry_point("safety_gate")
        graph.add_conditional_edges(
            "safety_gate",
            self._route_after_safety,
            {
                "blocked": "blocked",
                "crisis_response": "crisis_response",
                "initial_analysis": "initial_analysis",
            },
        )
        graph.add_conditional_edges(
            "initial_analysis",
            self._route_after_initial_analysis,
            {
                "crisis_response": "crisis_response",
                "risk_assessment": "risk_assessment",
                "dialogue": "dialogue",
            },
        )
        graph.add_conditional_edges(
            "risk_assessment", self._route_after_risk_assessment,
            {"follow_up_assessment": "follow_up_assessment", "profile_update": "profile_update"},
        )
        graph.add_edge("follow_up_assessment", "profile_update")
        graph.add_edge("profile_update", "intervention_plan")
        graph.add_edge("intervention_plan", "dialogue")
        graph.add_edge("dialogue", "evaluator")
        graph.add_edge("evaluator", "audit")
        graph.add_edge("blocked", "audit")
        graph.add_edge("crisis_response", "audit")
        graph.add_edge("audit", END)
        return graph.compile()

    @staticmethod
    def _ablation(_: OrchestrationRequest) -> AblationConfig:
        """Only the offline evaluation runner can enable an ablation context."""
        return active_ablation()

    async def _execute_node(
        self,
        node_name: WorkflowNodeName,
        state: OrchestratorWorkflowState,
        operation: Callable[[OrchestratorWorkflowState], Awaitable[OrchestratorWorkflowState]],
    ) -> OrchestratorWorkflowState:
        started = datetime.now(timezone.utc)
        try:
            next_state = await operation(state)
            finished = datetime.now(timezone.utc)
            metadata = {
                "workflow_engine": self.workflow_engine,
                "workflow_version": self.workflow_version,
            }
            node_metrics = next_state["values"].get("_node_metrics", {}).get(node_name)
            if isinstance(node_metrics, dict):
                metadata.update(node_metrics)
            next_state["trace_events"].append(
                AgentTraceEvent(
                    agent=node_name,
                    status="completed",
                    started_at=started,
                    finished_at=finished,
                    duration_ms=round((finished - started).total_seconds() * 1000),
                    metadata=metadata,
                )
            )
            return next_state
        except Exception as exc:
            finished = datetime.now(timezone.utc)
            state["trace_events"].append(
                AgentTraceEvent(
                    agent=node_name,
                    status="failed",
                    started_at=started,
                    finished_at=finished,
                    duration_ms=round((finished - started).total_seconds() * 1000),
                    error_code=type(exc).__name__,
                    metadata={
                        "workflow_engine": self.workflow_engine,
                        "workflow_version": self.workflow_version,
                    },
                )
            )
            state["status"] = "failed"
            raise

    async def _safety_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            request = current["request"]
            flags = self._ablation(request)
            if flags.enable_safety_gate:
                current["values"]["safety"] = await self.safety_gate.assess(
                    request.message, request.context,
                )
            else:
                current["values"]["safety"] = SafetyDecision(
                    decision="allow", redacted_message=request.message,
                    evidence=["offline_ablation:safety_gate_disabled"],
                )
            current["trace"].append("safety_gate")
            return current

        return await self._execute_node("safety_gate", state, operation)

    async def _initial_analysis_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            request = current["request"]
            safety = current["values"]["safety"]
            flags = self._ablation(request)
            subagent_duration_ms: dict[str, int] = {}

            async def timed(
                name: str,
                operation_factory: Callable[[], Awaitable[Any]],
            ) -> Any:
                started_at = perf_counter()
                try:
                    # 在任务真正开始运行后再创建协程。若任务在首次调度前被取消，
                    # 就不会遗留一个从未 await 的裸协程对象。
                    return await operation_factory()
                finally:
                    subagent_duration_ms[name] = round((perf_counter() - started_at) * 1000)

            def store_metrics() -> None:
                current["values"].setdefault("_node_metrics", {})["initial_analysis"] = {
                    "subagent_duration_ms": dict(subagent_duration_ms),
                }

            trend_points = self._trend_points(request.context.metadata)
            prior_crisis_state = (request.context.metadata or {}).get("crisis_state")
            background_tasks: list[asyncio.Task[Any]] = []
            try:
                if isinstance(prior_crisis_state, dict):
                    crisis_factory = lambda: self.crisis_agent.assess(
                        safety.redacted_message,
                        request.history,
                        prior_state=prior_crisis_state,
                    )
                else:
                    crisis_factory = lambda: self.crisis_agent.assess(
                        safety.redacted_message,
                        request.history,
                    )
                crisis_task = asyncio.create_task(timed("crisis_agent", crisis_factory))
                background_tasks.append(crisis_task)

                emotion_task = asyncio.create_task(
                    timed(
                        "emotion_agent",
                        lambda: self.emotion_agent.analyze(
                            safety.redacted_message,
                            request.history,
                        ),
                    )
                )
                background_tasks.append(emotion_task)
                intent_task = asyncio.create_task(
                    timed(
                        "rag_intent",
                        lambda: self._should_retrieve_knowledge(
                            safety.redacted_message, request.history,
                        ),
                    )
                )
                background_tasks.append(intent_task)

                crisis_result, emotion_result, should_retrieve = await asyncio.gather(
                    crisis_task, emotion_task, intent_task,
                )
                current["values"]["crisis"] = crisis_result
                current["values"]["emotion"] = emotion_result
                current["trace"].extend(["crisis_agent", "emotion_agent"])
                decision = await self._decide_route(
                    request,
                    rag_needed=should_retrieve,
                    crisis=crisis_result,
                    emotion=emotion_result,
                )
                current["values"]["route"] = decision
                current["values"].setdefault("_node_metrics", {})["initial_analysis"] = {
                    "route": decision["route"],
                    "route_reasons": decision["reasons"],
                    "route_scores": decision["route_scores"],
                    "hard_constraint_triggered": decision["hard_constraint_triggered"],
                }
                if crisis_result.level == "high" or crisis_result.action == "crisis_response":
                    current["values"]["trend"] = None
                    current["values"]["rag"] = None
                    subagent_duration_ms["trend_agent"] = 0
                    subagent_duration_ms["rag_agent"] = 0
                    store_metrics()
                    return current

                if decision["evidence_sufficient"]:
                    trend_started_at = perf_counter()
                    current["values"]["trend"] = self.trend_agent.analyze(trend_points)
                    subagent_duration_ms["trend_agent"] = round(
                        (perf_counter() - trend_started_at) * 1000
                    )
                    current["trace"].append("trend_agent")
                else:
                    current["values"]["trend"] = None
                    subagent_duration_ms["trend_agent"] = 0

                if decision["rag_needed"]:
                    rag_result = await timed(
                        "rag_agent",
                        lambda: self.rag_agent.retrieve(
                            safety.redacted_message, request.history,
                        ) if flags.enable_hierarchical_rag and flags.enable_reranker else self.rag_agent.retrieve(
                            safety.redacted_message, request.history,
                            hierarchical=flags.enable_hierarchical_rag,
                            rerank=flags.enable_reranker,
                        ),
                    )
                else:
                    rag_result = RAGAnalysis(
                        query=safety.redacted_message or "empty",
                        rewritten_query=(safety.redacted_message or "empty")[:500],
                        selected_categories=[],
                        top_k=getattr(self.rag_agent, "default_top_k", 5),
                        min_score=getattr(self.rag_agent, "default_min_score", 0.15),
                        has_evidence=False,
                        no_evidence_reason="not_applicable",
                        confidence=0.0,
                        retrieval_strategy="skipped",
                    )
                    subagent_duration_ms["rag_agent"] = 0
                current["values"]["rag"] = rag_result
                current["trace"].append("rag_agent")
                store_metrics()
                return current
            finally:
                # 任一分支提前返回、抛错或被外层超时取消时，都回收尚未完成的任务。
                pending_tasks = [task for task in background_tasks if not task.done()]
                for task in pending_tasks:
                    task.cancel()
                if pending_tasks:
                    await asyncio.gather(*pending_tasks, return_exceptions=True)

        return await self._execute_node("initial_analysis", state, operation)

    async def _risk_assessment_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            current["values"]["risk"] = self.risk_agent.assess(
                crisis=current["values"]["crisis"],
                emotion=current["values"]["emotion"],
                trend=current["values"].get("trend"),
                rag=current["values"].get("rag"),
            )
            current["trace"].append("risk_agent")
            return current

        return await self._execute_node("risk_assessment", state, operation)

    async def _profile_update_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            request = current["request"]
            safety = current["values"]["safety"]
            current["values"]["profile"] = self.profile_agent.analyze(
                message=safety.redacted_message,
                history=request.history,
                emotion=current["values"].get("emotion"),
                crisis=current["values"].get("crisis"),
                rag=current["values"].get("rag"),
                dialogue=None,
                existing_profile=request.context.metadata.get("profile")
                if request.context and request.context.metadata
                else None,
            )
            follow_up = current["values"].get("follow_up")
            if follow_up:
                plan = (request.context.metadata or {}).get("latest_intervention") or {}
                prior_strategy = str(plan.get("strategy") or "原干预方案")[:300]
                if follow_up.effectiveness == "improved":
                    incremental_item = ProfilePatchItem(
                        category="effective_advice",
                        value=f"{prior_strategy}：用户反馈有改善",
                        operation="add",
                        source="current_message",
                        evidence=follow_up.evidence[-1],
                        confidence=follow_up.confidence,
                    )
                elif follow_up.adherence in {"not_started", "partial"}:
                    incremental_item = ProfilePatchItem(
                        category="stress_source",
                        value="原干预方案执行受阻",
                        operation="add",
                        source="current_message",
                        evidence=follow_up.adjustment_reason,
                        confidence=follow_up.confidence,
                        sensitivity="sensitive",
                    )
                else:
                    incremental_item = ProfilePatchItem(
                        category="effective_advice",
                        value=f"{prior_strategy}：当前效果有限，需调整",
                        operation="update",
                        source="current_message",
                        evidence=follow_up.adjustment_reason,
                        confidence=follow_up.confidence,
                        sensitivity="sensitive",
                    )
                profile = current["values"]["profile"]
                current["values"]["profile"] = profile.model_copy(update={
                    "patch_items": [*profile.patch_items, incremental_item],
                    "summary": f"{profile.summary}；跟进画像增量：{incremental_item.value}",
                })
            current["trace"].append("profile_agent")
            return current

        return await self._execute_node("profile_update", state, operation)

    async def _follow_up_assessment_node(
        self, state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            request = current["request"]
            if not self._ablation(request).enable_follow_up_loop:
                current["values"]["follow_up"] = None
                return current
            current["values"]["follow_up"] = self.follow_up_agent.assess(
                message=current["values"]["safety"].redacted_message,
                latest_intervention=(request.context.metadata or {}).get("latest_intervention"),
                action_feedbacks=(request.context.metadata or {}).get("action_feedbacks") or [],
                trend=current["values"].get("trend"),
                emotion=current["values"].get("emotion"),
                risk=current["values"].get("risk"),
            )
            current["trace"].append("follow_up_agent")
            return current
        return await self._execute_node("follow_up_assessment", state, operation)

    async def _intervention_plan_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            current["values"]["intervention"] = self.intervention_agent.plan(
                crisis=current["values"]["crisis"],
                emotion=current["values"].get("emotion"),
                trend=current["values"].get("trend"),
                risk=current["values"].get("risk"),
                profile=current["values"].get("profile"),
                rag=current["values"].get("rag"),
            )
            follow_up = current["values"].get("follow_up")
            if follow_up:
                plan = current["values"]["intervention"]
                strategy_prefix = {
                    "keep": "跟进结论：原方案有效，保留并巩固。",
                    "adjust": "跟进结论：需降低负担并调整原方案。",
                    "replace": "跟进结论：原方案效果不足，替换为新的执行策略。",
                    "escalate": "跟进结论：需要升级人工关注与安全核查。",
                }[follow_up.decision]
                actions = self._follow_up_actions(
                    decision=follow_up.decision,
                    message=current["values"]["safety"].redacted_message,
                    existing_actions=self._prior_actions(current["request"].context.metadata) or plan.actions,
                    evidence=follow_up.evidence,
                    adjustment_reason=follow_up.adjustment_reason,
                    target_action_ids=follow_up.target_action_ids,
                )
                current["values"]["intervention"] = plan.model_copy(update={
                    "strategy": f"{strategy_prefix}{plan.strategy}",
                    "actions": actions,
                    "rationale": [*follow_up.evidence, follow_up.adjustment_reason, *plan.rationale][:8],
                    "requires_human_review": plan.requires_human_review or follow_up.decision == "escalate",
                })
            current["trace"].append("intervention_agent")
            return current

        return await self._execute_node("intervention_plan", state, operation)

    @staticmethod
    def _follow_up_actions(
        *,
        decision: str,
        message: str,
        existing_actions: list[InterventionAction],
        evidence: list[str],
        adjustment_reason: str,
        target_action_ids: list[str],
    ) -> list[InterventionAction]:
        """跟进决策必须影响行动项，不能只改策略文案。"""
        if decision == "keep":
            if target_action_ids:
                return existing_actions
            return [
                *existing_actions,
                InterventionAction(
                    priority=len(existing_actions) + 1,
                    action_type="active_check_in",
                    title="巩固并记录效果",
                    description="继续执行当前方案，并在接下来 3 天简要记录执行情况和主观变化。",
                    rationale="用户反馈已有改善，需要先巩固有效做法而不是频繁更换方案。",
                    evidence=evidence[:3],
                ),
            ]
        if decision == "adjust":
            adjusted = list(existing_actions)
            targets = set(target_action_ids)
            for index, action in enumerate(adjusted):
                if targets and action.action_id not in targets:
                    continue
                adjusted[index] = action.model_copy(update={
                    "title": f"低负担版：{action.title}",
                    "description": f"将原步骤拆成 2 分钟的小任务；{action.description}",
                    "rationale": "本轮反馈显示原方案未充分执行，先降低执行门槛，不直接判定原方案无效。",
                    "evidence": evidence[:3],
                })
                if not targets:
                    break
            return adjusted
        if decision == "replace":
            if target_action_ids:
                alternatives = Orchestrator._follow_up_actions(
                    decision="replace", message=message, existing_actions=existing_actions,
                    evidence=evidence, adjustment_reason=adjustment_reason, target_action_ids=[],
                )
                targets = set(target_action_ids)
                merged: list[InterventionAction] = []
                inserted = False
                for action in existing_actions:
                    if action.action_id not in targets:
                        merged.append(action)
                        continue
                    if not inserted:
                        merged.extend(
                            alternative.model_copy(update={"action_id": f"{action.action_id}-alt-{index + 1}"})
                            for index, alternative in enumerate(alternatives)
                        )
                        inserted = True
                return [action.model_copy(update={"priority": index + 1}) for index, action in enumerate(merged)]
            if any(term in message for term in ("睡", "失眠", "入睡", "夜醒")):
                return [
                    InterventionAction(
                        priority=1,
                        action_type="self_regulation",
                        title="睡前一小时减少刷屏",
                        description="从今晚开始，在计划入睡前 1 小时停止刷短视频和高刺激内容，改为低刺激的洗漱、整理或安静活动。",
                        rationale="原方案已执行但睡眠困扰仍持续，改用不同的睡前刺激管理策略。",
                        related_profile_categories=["sleep_status"],
                        evidence=evidence[:3],
                    ),
                    InterventionAction(
                        priority=2,
                        action_type="active_check_in",
                        title="连续三天记录入睡情况",
                        description="每晚只记录上床时间、预计入睡时长和夜醒次数，用于判断新的调整是否有效。",
                        rationale="需要以连续记录替代单次感受，形成下一轮调整依据。",
                        related_profile_categories=["sleep_status"],
                        evidence=[adjustment_reason],
                    ),
                    InterventionAction(
                        priority=3,
                        action_type="self_regulation",
                        title="保留两分钟呼吸作为辅助",
                        description="呼吸练习不再作为唯一核心方法；若愿意，可在睡前仅做 2 分钟，感到负担时可跳过。",
                        rationale="保留低负担辅助动作，同时避免重复依赖已显示效果有限的单一方案。",
                        related_profile_categories=["coping_method", "sleep_status"],
                        evidence=evidence[:2],
                    ),
                ]
            return [
                InterventionAction(
                    priority=1,
                    action_type="self_regulation",
                    title="改用三分钟状态记录",
                    description="每天选择一个固定时段，用三分钟记录最困扰的情境、情绪强度和已尝试的方法。",
                    rationale="原方案效果有限，先切换到可观察、可用于下一轮判断的替代策略。",
                    evidence=evidence[:3],
                ),
                InterventionAction(
                    priority=2,
                    action_type="social_support",
                    title="选择一位可信任的人简短沟通",
                    description="如愿意，向一位朋友、家人或老师说明近况，并约定一次简短的关心或陪伴。",
                    rationale="在替换原自助方案时补充现实支持资源。",
                    evidence=[adjustment_reason],
                ),
            ]
        if decision == "escalate":
            return [
                InterventionAction(
                    priority=1,
                    action_type="human_review",
                    title="优先连接线下支持",
                    description="建议尽快联系可信任的家人、老师、学校心理中心或当地专业支持资源，并说明当前状态有加重。",
                    rationale="跟进结果提示需要升级人工关注，不宜仅依赖线上自助方案。",
                    evidence=evidence[:4],
                )
            ]
        return existing_actions

    @staticmethod
    def _prior_actions(metadata: dict[str, Any] | None) -> list[InterventionAction]:
        """跟进时继承上一版方案；只有被反馈的行动才会被调整或替代。"""
        raw = (metadata or {}).get("latest_intervention") or {}
        actions = raw.get("actions") if isinstance(raw, dict) else None
        if isinstance(actions, str):
            try:
                actions = json.loads(actions)
            except json.JSONDecodeError:
                return []
        if not isinstance(actions, list):
            return []
        parsed: list[InterventionAction] = []
        for item in actions:
            try:
                parsed.append(InterventionAction.model_validate(item))
            except (TypeError, ValueError):
                continue
        return parsed

    async def _dialogue_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            request = current["request"]
            safety = current["values"]["safety"]
            rag = current["values"].get("rag")
            route = current["values"].get("route")
            if (
                isinstance(route, dict)
                and route.get("route") == "knowledge_support"
                and rag
                and not rag.has_evidence
            ):
                reason = (
                    "当前本地知识库没有检索到足以支持这一具体问题的资料，"
                    "我不想据此编造做法或引用。"
                )
                reply = (
                    f"{reason}\n\n"
                    "如果你愿意，可以补充你所在的学校、最困扰的具体情境或希望了解的求助方式，"
                    "我会基于可核实资料继续帮你查找。若这件事让你感到明显难以承受，"
                    "也可以联系学校心理中心、辅导员或当地专业支持。"
                )
                callback = _STREAM_CALLBACK.get()
                if callback is not None:
                    await callback(reply)
                current["values"]["chat"] = ModelChatResponse(
                    content=reply,
                    model="trusted_abstention",
                    usage={"trusted_abstention": True, "reason": rag.no_evidence_reason},
                )
                current["trace"].append("trusted_abstention")
                return current
            profile = current["values"].get("profile")
            intervention = current["values"].get("intervention")
            kwargs = {
                "crisis": current["values"]["crisis"],
                "risk": current["values"].get("risk"),
                "rag_citations": rag.citations if rag and rag.has_evidence else [],
                "profile": profile.model_dump(mode="json") if profile else None,
                "intervention": intervention.model_dump(mode="json") if intervention else None,
            }
            callback = _STREAM_CALLBACK.get()
            if callback is None:
                current["values"]["chat"] = await self.chat_agent.respond(
                    safety.redacted_message, request.history, **kwargs
                )
            else:
                current["values"]["chat"] = await self.chat_agent.respond_stream(
                    safety.redacted_message,
                    request.history,
                    on_chunk=callback,
                    **kwargs,
                )
            current["trace"].append("chat_agent")
            return current

        return await self._execute_node("dialogue", state, operation)

    async def _evaluator_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            if not self._ablation(current["request"]).enable_evaluator:
                chat_result = current["values"]["chat"]
                current["values"]["reply"] = chat_result.content
                current["values"]["model"] = chat_result.model
                return current
            safety = current["values"]["safety"]
            crisis = current["values"]["crisis"]
            rag = current["values"].get("rag")
            chat_result = current["values"]["chat"]
            evaluation = self.evaluator_agent.evaluate(
                reply=chat_result.content,
                crisis=crisis,
                safety=safety,
                rag=rag,
                risk=current["values"].get("risk"),
                trend=current["values"].get("trend"),
                intervention=current["values"].get("intervention"),
            )
            current["values"]["evaluator"] = evaluation
            current["values"]["reply"] = evaluation.final_reply
            current["values"]["model"] = (
                f"{chat_result.model}+evaluator"
                if evaluation.corrected_reply
                else chat_result.model
            )
            current["trace"].append("evaluator_agent")
            return current

        return await self._execute_node("evaluator", state, operation)

    async def _audit_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            request = current["request"]
            values = current["values"]
            safety = values.get("safety")
            current["values"]["audit"] = self.audit_agent.create_audit(
                context=request.context,
                original_message=request.message,
                redacted_message=safety.redacted_message if safety else None,
                history_count=len(request.history),
                workflow_engine=self.workflow_engine,
                workflow_version=self.workflow_version,
                trace=current["trace"] + ["audit_agent"],
                trace_events=current["trace_events"],
                route=(
                    values.get("route", {}).get("route")
                    if isinstance(values.get("route"), dict)
                    else None
                ),
                route_decision=values.get("route") if isinstance(values.get("route"), dict) else None,
                agent_versions=self._agent_versions(),
                prompt_versions=self._prompt_versions(),
                safety=safety,
                crisis=values.get("crisis"),
                emotion=values.get("emotion"),
                rag=values.get("rag"),
                trend=values.get("trend"),
                risk=values.get("risk"),
                profile=values.get("profile"),
                intervention=values.get("intervention"),
                evaluator=values.get("evaluator"),
                status=current["status"] if current["status"] in {"completed", "partial", "failed"} else "completed",
            )
            current["trace"].append("audit_agent")
            return current

        return await self._execute_node("audit", state, operation)

    async def _blocked_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            current["values"]["crisis"] = CrisisAnalysis(
                level="low",
                confidence=1.0,
                evidence=["请求被安全闸门拦截"],
            )
            current["values"]["reply"] = "这个请求无法处理。请换一种方式描述你的问题。"
            current["values"]["model"] = "safety_policy"
            current["trace"].append("blocked")
            return current

        return await self._execute_node("blocked", state, operation)

    async def _crisis_response_node(
        self,
        state: OrchestratorWorkflowState,
    ) -> OrchestratorWorkflowState:
        async def operation(current: OrchestratorWorkflowState) -> OrchestratorWorkflowState:
            safety = current["values"]["safety"]
            request = current["request"]
            crisis = current["values"].get("crisis")
            if crisis is None:
                prior_crisis_state = (request.context.metadata or {}).get("crisis_state")
                if isinstance(prior_crisis_state, dict):
                    crisis = await self.crisis_agent.assess(
                        safety.redacted_message, request.history, prior_state=prior_crisis_state
                    )
                else:
                    crisis = await self.crisis_agent.assess(safety.redacted_message, request.history)

            route_decision = self.risk_router.decide(RoutingInput(
                crisis_level="high",
                crisis_action="crisis_response",
                safety_escalated=safety.decision == "escalate",
                knowledge_need=0.0,
            )).model_dump()
            route_decision["reasons"] = ["检测到即时危机信号，已切换危机响应路径"]
            current["values"]["route"] = route_decision

            # 保留 CrisisAgent 的真实自伤/他伤、计划、工具、时间、地点与证据，
            # 此节点只补充安全门升级状态和固定危机应答，禁止统一伪造成“自伤+计划”。
            merged_evidence = list(dict.fromkeys(crisis.evidence + (safety.evidence or [])))[:8]
            current["values"]["crisis"] = crisis.model_copy(
                update={
                    "level": "high",
                    "immediacy": "immediate" if crisis.time_present else crisis.immediacy,
                    "confidence": max(crisis.confidence, 0.98),
                    "evidence": merged_evidence or ["检测到即时安全风险"],
                    "action": "crisis_response",
                    "requires_human_review": True,
                    "hard_rule_triggered": True,
                    "decision_source": "rules_over_model",
                    "crisis_response": CRISIS_RESPONSE_TEMPLATES["high"],
                }
            )
            crisis = current["values"]["crisis"]
            # 危机路径不进入常规风险节点，但必须留下正式的最高级风险记录，
            # 供 Java 持久化、审计和人工接管使用。
            current["values"]["risk"] = RiskAnalysis(
                risk_level="high",
                risk_score=1.0,
                confidence=max(0.98, crisis.confidence),
                emotion_risk=0.0,
                trend_risk=0.0,
                crisis_detected=True,
                evidence=crisis.evidence,
                main_factors=["即时危机安全信号", *crisis.evidence[:3]],
                recommendation="已触发危机响应：立即优先实施安全保护与人工接管。",
                requires_human_review=True,
                hard_rule_applied=True,
                calculation_trace=[
                    RiskCalculationItem(
                        name="crisis_override",
                        formula="crisis_response => risk_level=high, risk_score=1.0",
                        value=1.0,
                        weight=1.0,
                        contribution=1.0,
                        evidence=crisis.evidence[:5],
                    )
                ],
                decision_source="hard_rule",
                model_explanation="危机路径按最高风险等级记录，不等待常规综合评估。",
            )
            current["values"]["reply"] = current["values"]["crisis"].crisis_response
            current["values"]["model"] = "rule_and_safety_response"
            current["trace"].extend(["crisis_response", "risk_assessment:crisis_override"])
            return current

        return await self._execute_node("crisis_response", state, operation)

    @staticmethod
    def _route_after_safety(state: OrchestratorWorkflowState) -> str:
        safety = state["values"]["safety"]
        if safety.decision == "block":
            return "blocked"
        if safety.decision == "escalate":
            return "crisis_response"
        return "initial_analysis"

    @staticmethod
    def _route_after_initial_analysis(state: OrchestratorWorkflowState) -> str:
        crisis = state["values"]["crisis"]
        if crisis.level == "high" or crisis.action == "crisis_response":
            return "crisis_response"
        decision = state["values"].get("route")
        if isinstance(decision, dict) and decision.get("evidence_sufficient"):
            return "risk_assessment"
        return "dialogue"

    def _route_after_risk_assessment(self, state: OrchestratorWorkflowState) -> str:
        route = state["values"].get("route")
        if (self._ablation(state["request"]).enable_follow_up_loop
                and isinstance(route, dict) and route.get("route") == "follow_up_support"):
            return "follow_up_assessment"
        return "profile_update"

    @staticmethod
    def _trend_points(metadata: dict[str, Any] | None) -> list[EmotionPoint]:
        raw_points = (metadata or {}).get("trend_points")
        if not isinstance(raw_points, list):
            return []
        points: list[EmotionPoint] = []
        for raw in raw_points[-30:]:
            try:
                points.append(EmotionPoint.model_validate(raw))
            except (TypeError, ValueError):
                continue
        return points

    def _agent_versions(self) -> dict[str, str]:
        versions: dict[str, str] = {}
        for descriptor in self.registry.list():
            versions[descriptor.name] = descriptor.version
        return versions

    def _prompt_versions(self) -> dict[str, str]:
        prompt_versions: dict[str, str] = {}
        for name in (
            "chat_agent",
            "emotion_agent",
            "crisis_agent",
            "rag_agent",
            "trend_agent",
            "risk_agent",
            "profile_agent",
            "intervention_agent",
            "follow_up_agent",
            "evaluator_agent",
            "audit_agent",
        ):
            agent = getattr(self, name, None)
            prompt_name = getattr(agent, "prompt_name", None)
            prompt_version = getattr(agent, "prompt_version", None)
            if prompt_name and prompt_version:
                prompt_versions[str(prompt_name)] = str(prompt_version)
            else:
                agent_name = getattr(agent, "name", name)
                version = getattr(agent, "version", None)
                if version:
                    prompt_versions[f"{agent_name}_rules"] = str(version)
        return prompt_versions
