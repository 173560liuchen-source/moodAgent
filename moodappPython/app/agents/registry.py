from dataclasses import dataclass
from typing import Any, Callable

from ..model_gateway import ModelGateway
from .audit_agent import AuditAgent
from .chat_agent import ChatAgent
from .crisis_agent import CrisisAgent
from .emotion_agent import EmotionAgent
from .evaluator_agent import EvaluatorAgent
from .follow_up_agent import FollowUpAgent
from .intervention_agent import InterventionAgent
from .profile_agent import ProfileAgent
from .rag_agent import RAGAgent
from .risk_agent import RiskAgent
from .safety_gate import SafetyGateAgent
from .trend_agent import TrendAgent


@dataclass(frozen=True)
class AgentDescriptor:
    name: str
    version: str
    capabilities: tuple[str, ...]
    criticality: str
    factory: Callable[[], Any]


class AgentRegistry:
    """集中管理智能体元数据、版本和实例工厂。"""

    def __init__(self) -> None:
        self._descriptors: dict[str, AgentDescriptor] = {}

    def register(self, descriptor: AgentDescriptor) -> None:
        if descriptor.name in self._descriptors:
            raise ValueError(f"agent already registered: {descriptor.name}")
        self._descriptors[descriptor.name] = descriptor

    def get(self, name: str) -> AgentDescriptor:
        try:
            return self._descriptors[name]
        except KeyError as exc:
            raise KeyError(f"agent not registered: {name}") from exc

    def create(self, name: str) -> Any:
        return self.get(name).factory()

    def list(self) -> list[AgentDescriptor]:
        return sorted(self._descriptors.values(), key=lambda item: item.name)


def build_default_registry(gateway: ModelGateway) -> AgentRegistry:
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
        capabilities=("self_harm_screening", "immediate_danger"),
        criticality="critical", factory=lambda: CrisisAgent(gateway),
    ))
    registry.register(AgentDescriptor(
        name="chat", version=ChatAgent.version,
        capabilities=("empathetic_dialogue", "streaming_ready"),
        criticality="normal", factory=lambda: ChatAgent(gateway),
    ))
    registry.register(AgentDescriptor(
        name="emotion", version=EmotionAgent.version,
        capabilities=("emotion_structuring", "evidence_extraction"),
        criticality="high", factory=lambda: EmotionAgent(gateway),
    ))
    registry.register(AgentDescriptor(
        name="rag", version=RAGAgent.version,
        capabilities=("pgvector_retrieval", "rerank", "citation_traceability", "no_evidence_policy"),
        criticality="high", factory=RAGAgent,
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
    return registry
