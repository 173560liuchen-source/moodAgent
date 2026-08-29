import asyncio
import unittest

from app.ablation import AblationConfig, active_ablation, offline_ablation
from app.agents.orchestrator import Orchestrator
from app.schemas import OrchestrationRequest


class AblationSwitchTests(unittest.TestCase):
    def test_switches_are_active_only_inside_offline_context(self):
        self.assertTrue(active_ablation().enable_safety_gate)

        with offline_ablation(AblationConfig(enable_safety_gate=False)):
            self.assertFalse(active_ablation().enable_safety_gate)

        self.assertTrue(active_ablation().enable_safety_gate)

    def test_unknown_switches_are_ignored(self):
        config = AblationConfig.from_mapping({
            "enable_reranker": False,
            "untrusted_switch": False,
        })
        self.assertFalse(config.enable_reranker)
        self.assertTrue(config.enable_safety_gate)

    def test_disabling_risk_router_uses_legacy_policy_only_for_offline_ablation(self):
        orchestrator = Orchestrator()
        request = OrchestrationRequest(message="失眠有什么调整方法？")

        enabled = asyncio.run(orchestrator._decide_route(request, rag_needed=True))
        with offline_ablation(AblationConfig(enable_risk_router=False)):
            disabled = asyncio.run(orchestrator._decide_route(request, rag_needed=True))

        self.assertEqual(enabled["policy_version"], "risk-constrained-router-1.1.0")
        self.assertEqual(disabled["policy_version"], "legacy-route-rules-7.2.0")
        self.assertEqual(disabled["route"], "knowledge_support")
        self.assertTrue(active_ablation().enable_risk_router)
