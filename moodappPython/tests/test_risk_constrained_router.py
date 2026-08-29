import unittest

from app.agents.risk_constrained_router import RiskConstrainedRouter, RoutingInput


class RiskConstrainedRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = RiskConstrainedRouter()

    def test_high_crisis_is_a_hard_constraint(self):
        decision = self.router.decide(RoutingInput(
            crisis_level="high", knowledge_need=1.0, follow_up_need=1.0,
        ))
        self.assertEqual(decision.route, "crisis_response")
        self.assertTrue(decision.hard_constraint_triggered)
        self.assertFalse(decision.rag_needed)

    def test_follow_up_beats_general_assessment(self):
        decision = self.router.decide(RoutingInput(
            emotion_load=0.8, trend_load=0.7, follow_up_need=0.9,
            assessment_evidence=True, user_turn_count=4,
        ))
        self.assertEqual(decision.route, "follow_up_support")
        self.assertGreater(decision.route_scores.follow_up_support, 0.6)

    def test_medium_safety_signal_uses_assessment_and_grounded_resources(self):
        decision = self.router.decide(RoutingInput(
            crisis_level="medium",
            crisis_action="check_in",
            emotion_load=0.7,
            user_turn_count=1,
        ))

        self.assertEqual(decision.route, "structured_assessment")
        self.assertTrue(decision.evidence_sufficient)
        self.assertTrue(decision.rag_needed)
        self.assertFalse(decision.hard_constraint_triggered)

    def test_medium_safety_overrides_ordinary_follow_up_route(self):
        decision = self.router.decide(RoutingInput(
            crisis_level="medium",
            crisis_action="check_in",
            follow_up_need=1.0,
        ))

        self.assertEqual(decision.route, "structured_assessment")

    def test_assessment_requires_longitudinal_evidence(self):
        without_history = self.router.decide(RoutingInput(emotion_load=0.9))
        with_history = self.router.decide(RoutingInput(
            emotion_load=0.9, trend_load=0.7, assessment_evidence=True, user_turn_count=3,
        ))
        self.assertNotEqual(without_history.route, "structured_assessment")
        self.assertEqual(with_history.route, "structured_assessment")

    def test_knowledge_question_selects_rag_path(self):
        decision = self.router.decide(RoutingInput(knowledge_need=0.9))
        self.assertEqual(decision.route, "knowledge_support")
        self.assertTrue(decision.rag_needed)

    def test_explicit_knowledge_need_beats_ordinary_assessment_history(self):
        decision = self.router.decide(RoutingInput(
            emotion_load=0.35,
            trend_load=0.2,
            knowledge_need=1.0,
            assessment_evidence=True,
            user_turn_count=6,
        ))
        self.assertEqual(decision.route, "knowledge_support")
        self.assertTrue(decision.rag_needed)

    def test_turn_count_alone_does_not_force_assessment(self):
        decision = self.router.decide(RoutingInput(
            emotion_load=0.25,
            user_turn_count=8,
        ))
        self.assertEqual(decision.route, "exploratory_support")

    def test_plain_disclosure_stays_exploratory(self):
        decision = self.router.decide(RoutingInput(emotion_load=0.3, user_turn_count=1))
        self.assertEqual(decision.route, "exploratory_support")
