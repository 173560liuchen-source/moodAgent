from __future__ import annotations

import asyncio
from typing import Literal

from ..agents.audit_agent import AuditAgent
from ..agents.chat_agent import ChatAgent
from ..agents.crisis_agent import CrisisAgent
from ..agents.emotion_agent import EmotionAgent
from ..agents.evaluator_agent import EvaluatorAgent
from ..agents.follow_up_agent import FollowUpAgent
from ..agents.intervention_agent import InterventionAgent
from ..agents.orchestrator import Orchestrator
from ..agents.profile_agent import ProfileAgent
from ..agents.rag_agent import RAGAgent, RAGAnalysis
from ..agents.registry import AgentDescriptor, AgentRegistry
from ..agents.risk_agent import RiskAgent
from ..agents.safety_gate import SafetyGateAgent
from ..agents.trend_agent import TrendAgent
from ..model_gateway import ModelGateway, ModelGatewayError
from ..rag.contracts import RetrievalError
from ..schemas import ModelChatRequest, ModelChatResponse


FaultMode = Literal["model_api_failure", "model_timeout", "invalid_json", "rag_failure"]


class FailingModelGateway(ModelGateway):
    async def chat(self, request: ModelChatRequest) -> ModelChatResponse:
        raise ModelGatewayError("fault_injection:model_api_failure")


class InvalidJSONModelGateway(ModelGateway):
    async def chat(self, request: ModelChatRequest) -> ModelChatResponse:
        return ModelChatResponse(
            content="这不是 JSON，也不符合结构化输出协议。",
            model="fault_injection_invalid_json",
            usage={"fault_injection": True, "mode": "invalid_json"},
        )


class TimeoutModelGateway(ModelGateway):
    async def chat(self, request: ModelChatRequest) -> ModelChatResponse:
        raise asyncio.TimeoutError("fault_injection:model_timeout")


class FaultyRAGAgent(RAGAgent):
    version = "fault-rag-8.2.0"

    async def retrieve(self, message, history=None, *, top_k=None, min_score=None) -> RAGAnalysis:
        return RAGAnalysis(
            query=message.strip() or "empty",
            rewritten_query=message.strip() or "empty",
            selected_categories=[],
            top_k=top_k or self.default_top_k,
            min_score=min_score if min_score is not None else self.default_min_score,
            has_evidence=False,
            no_evidence_reason="retrieval_error",
            citations=[],
            errors=[
                RetrievalError(
                    error_code="FaultInjectedRAGFailure",
                    message="fault_injection:rag_failure",
                )
            ],
            confidence=0.0,
        )


def build_fault_injected_orchestrator(mode: FaultMode) -> Orchestrator:
    gateway: ModelGateway
    crisis_gateway: ModelGateway
    if mode == "model_api_failure":
        gateway = FailingModelGateway()
        crisis_gateway = gateway
    elif mode == "model_timeout":
        crisis_gateway = TimeoutModelGateway()
        gateway = FailingModelGateway()
    elif mode == "invalid_json":
        gateway = InvalidJSONModelGateway()
        crisis_gateway = gateway
    else:
        gateway = ModelGateway()
        crisis_gateway = gateway

    registry = AgentRegistry()
    registry.register(AgentDescriptor(
        name="audit", version=AuditAgent.version,
        capabilities=("decision_chain", "version_snapshot", "data_minimization", "trace_summary"),
        criticality="critical", factory=AuditAgent,
    ))
    registry.register(AgentDescriptor(
        name="safety_gate", version=SafetyGateAgent.version,
        capabilities=("pii_detection", "prompt_injection", "redaction"),
        criticality="critical", factory=SafetyGateAgent,
    ))
    registry.register(AgentDescriptor(
        name="crisis", version=CrisisAgent.version,
        capabilities=("self_harm_screening", "immediate_danger", "fault_fallback"),
        criticality="critical", factory=lambda: CrisisAgent(crisis_gateway),
    ))
    registry.register(AgentDescriptor(
        name="chat", version=ChatAgent.version,
        capabilities=("empathetic_dialogue", "model_failure_fallback"),
        criticality="normal", factory=lambda: ChatAgent(gateway),
    ))
    registry.register(AgentDescriptor(
        name="emotion", version=EmotionAgent.version,
        capabilities=("emotion_structuring", "json_repair", "fault_fallback"),
        criticality="high", factory=lambda: EmotionAgent(gateway),
    ))
    registry.register(AgentDescriptor(
        name="rag", version=FaultyRAGAgent.version if mode == "rag_failure" else RAGAgent.version,
        capabilities=("pgvector_retrieval", "rerank", "citation_traceability", "fault_fallback"),
        criticality="high", factory=FaultyRAGAgent if mode == "rag_failure" else RAGAgent,
    ))
    registry.register(AgentDescriptor(
        name="evaluator", version=EvaluatorAgent.version,
        capabilities=("safety_evaluation", "citation_integrity", "risk_consistency", "deterministic_repair"),
        criticality="critical", factory=EvaluatorAgent,
    ))
    registry.register(AgentDescriptor(
        name="follow_up", version=FollowUpAgent.version,
        capabilities=("adherence_assessment", "effectiveness_comparison", "plan_adjustment_decision"),
        criticality="high", factory=FollowUpAgent,
    ))
    registry.register(AgentDescriptor(
        name="profile", version=ProfileAgent.version,
        capabilities=("profile_patch", "source_confidence", "user_control_policy", "no_persistent_chat"),
        criticality="high", factory=ProfileAgent,
    ))
    registry.register(AgentDescriptor(
        name="intervention", version=InterventionAgent.version,
        capabilities=("risk_aligned_strategy", "profile_aware_actions", "crisis_first", "human_review_policy"),
        criticality="critical", factory=InterventionAgent,
    ))
    registry.register(AgentDescriptor(
        name="trend", version=TrendAgent.version,
        capabilities=("time_series_analysis", "7d_30d_windows", "intervention_comparison"),
        criticality="high", factory=TrendAgent,
    ))
    registry.register(AgentDescriptor(
        name="risk", version=RiskAgent.version,
        capabilities=("rule_based_risk", "explainable_score"),
        criticality="critical", factory=RiskAgent,
    ))
    orchestrator = Orchestrator(registry)
    orchestrator.workflow_version = "8.2.0-fault-injection"
    return orchestrator
