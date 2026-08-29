import gc
import unittest
import warnings

from app.agents.crisis_agent import CrisisAnalysis
from app.agents.emotion_agent import EmotionAnalysis
from app.agents.orchestrator import Orchestrator
from app.agents.rag_agent import RAGAnalysis
from app.agents.safety_gate import SafetyDecision
from app.model_gateway import ModelChatResponse
from app.schemas import ChatMessage, OrchestrationRequest


class _CrisisStub:
    async def assess(self, message, history):
        return CrisisAnalysis(level="low", confidence=0.9, evidence=[])


class _ImmediateHighCrisisStub:
    async def assess(self, message, history):
        return CrisisAnalysis(
            level="high",
            confidence=1.0,
            evidence=["测试高风险分支"],
            action="crisis_response",
        )


class _EmotionStub:
    async def analyze(self, message, history):
        return EmotionAnalysis(
            emotion="anxious",
            anxiety=0.8,
            stress=0.75,
            depression=0.2,
            loneliness=0.1,
            confidence=0.9,
            evidence=["压力很大", "睡不着"],
        )


class _MildEmotionStub:
    async def analyze(self, message, history):
        return EmotionAnalysis(
            emotion="tired",
            anxiety=0.3,
            stress=0.35,
            depression=0.1,
            loneliness=0.1,
            confidence=0.85,
            evidence=["睡眠困扰仍在持续"],
        )


class _RagStub:
    async def retrieve(self, message, history):
        return RAGAnalysis(
            query=message,
            rewritten_query=message,
            selected_categories=[],
            top_k=5,
            min_score=0.2,
            has_evidence=False,
            no_evidence_reason="no_relevant_chunks",
            confidence=0.0,
        )


class _ChatStub:
    def __init__(self):
        self.received_risk = None
        self.received_intervention = None

    async def respond(self, message, history, **kwargs):
        self.received_risk = kwargs.get("risk")
        self.received_intervention = kwargs.get("intervention")
        return ModelChatResponse(content="我们先从一个小步骤开始。", model="stub")


class _NoEvidenceRagStub:
    default_top_k = 5
    default_min_score = 0.2

    async def retrieve(self, message, history):
        return RAGAnalysis(
            query=message, rewritten_query=message, selected_categories=[], top_k=5, min_score=0.2,
            has_evidence=False, no_evidence_reason="no_relevant_chunks", confidence=0.0,
        )


class OrchestratorTrendRiskTest(unittest.IsolatedAsyncioTestCase):
    async def test_first_turn_uses_exploratory_route_without_full_assessment(self):
        orchestrator = Orchestrator()
        request = OrchestrationRequest(message="我今天有点累，想找人聊聊")

        decision = await orchestrator._decide_route(request, rag_needed=False)

        self.assertEqual(decision["route"], "exploratory_support")
        self.assertFalse(decision["evidence_sufficient"])

    async def test_first_turn_knowledge_question_uses_knowledge_route(self):
        orchestrator = Orchestrator()
        request = OrchestrationRequest(message="失眠有什么调整方法？")

        decision = await orchestrator._decide_route(request, rag_needed=True)

        self.assertEqual(decision["route"], "knowledge_support")
        self.assertTrue(decision["rag_needed"])
        self.assertFalse(decision["evidence_sufficient"])

    async def test_first_turn_medium_safety_signal_uses_structured_assessment(self):
        orchestrator = Orchestrator()
        request = OrchestrationRequest(message="班里有人一直威胁我，不让我告诉老师。")

        decision = await orchestrator._decide_route(
            request,
            rag_needed=False,
            crisis=CrisisAnalysis(
                level="medium",
                action="check_in",
                requires_human_review=True,
            ),
        )

        self.assertEqual(decision["route"], "structured_assessment")
        self.assertTrue(decision["evidence_sufficient"])
        self.assertTrue(decision["rag_needed"])

    async def test_knowledge_request_without_evidence_uses_trusted_abstention(self):
        orchestrator = Orchestrator()
        chat_stub = _ChatStub()
        orchestrator.crisis_agent = _CrisisStub()
        orchestrator.emotion_agent = _MildEmotionStub()
        orchestrator.rag_agent = _NoEvidenceRagStub()
        orchestrator.chat_agent = chat_stub
        result = await orchestrator.run(OrchestrationRequest(message="有没有适合我的神秘疗法？"))
        self.assertIn("没有检索到足以支持", result.reply)
        self.assertIn("trusted_abstention", result.trace)
        self.assertNotIn("chat_agent", result.trace)

    async def test_accumulated_user_context_enables_structured_assessment(self):
        orchestrator = Orchestrator()
        request = OrchestrationRequest(
            message="已经两周了，白天也不想上课。",
            history=[
                ChatMessage(role="user", content="最近总睡不着"),
                ChatMessage(role="assistant", content="这样的情况持续多久了？"),
                ChatMessage(role="user", content="考试压力很大"),
            ],
        )

        decision = await orchestrator._decide_route(request, rag_needed=False)

        self.assertEqual(decision["route"], "structured_assessment")
        self.assertTrue(decision["evidence_sufficient"])

    async def test_stable_mild_history_does_not_force_structured_assessment(self):
        orchestrator = Orchestrator()
        request = OrchestrationRequest.model_validate({
            "message": "今天上课有点累，心情一般，不过晚上准备早点休息。",
            "history": [
                {"role": "user", "content": "前几天有点忙。"},
                {"role": "assistant", "content": "可以先适当休息。"},
                {"role": "user", "content": "现在生活还能正常维持。"},
            ],
            "context": {"metadata": {"trend_points": [
                {"timestamp": "2026-08-20T00:00:00Z", "anxiety": 0.2, "stress": 0.25, "depression": 0.1},
                {"timestamp": "2026-08-21T00:00:00Z", "anxiety": 0.2, "stress": 0.2, "depression": 0.1},
                {"timestamp": "2026-08-22T00:00:00Z", "anxiety": 0.15, "stress": 0.2, "depression": 0.1},
            ]}},
        })

        decision = await orchestrator._decide_route(request, rag_needed=False)

        self.assertEqual(decision["route"], "exploratory_support")
        self.assertFalse(decision["features"]["assessment_evidence"])

    async def test_stale_action_feedback_does_not_capture_new_knowledge_topic(self):
        orchestrator = Orchestrator()
        request = OrchestrationRequest.model_validate({
            "message": "如果学校心理中心暂时预约不上，我还可以联系哪些校内人员？",
            "context": {"metadata": {
                "latest_intervention": {"id": 18, "strategy": "任务拆分"},
                "action_feedbacks": [{"actionId": "a1", "executionStatus": "completed"}],
            }},
        })

        decision = await orchestrator._decide_route(request, rag_needed=True)

        self.assertEqual(decision["route"], "knowledge_support")
        self.assertEqual(decision["features"]["follow_up_need"], 0.0)

    async def test_explicit_plan_adjustment_keeps_follow_up_route(self):
        orchestrator = Orchestrator()
        request = OrchestrationRequest.model_validate({
            "message": "那就帮我调整成每天只做一个最小任务吧。",
            "context": {"metadata": {
                "latest_intervention": {"id": 19, "strategy": "每天完成三件事"},
            }},
        })

        decision = await orchestrator._decide_route(request, rag_needed=False)

        self.assertEqual(decision["route"], "follow_up_support")
        self.assertEqual(decision["features"]["follow_up_need"], 1.0)

    async def test_latest_low_risk_knowledge_questions_use_knowledge_route(self):
        orchestrator = Orchestrator()
        messages = (
            "我想预约学校心理中心，通常有哪些入口，需要提前准备什么信息？",
            "最近总是很晚才能睡着，有哪些容易坚持、负担比较小的改善方法？",
            "考试临近时总是很紧张，复习效率也下降了，有哪些可以马上尝试的减压方法？",
            "你直接告诉我，我最近情绪低落，是不是已经得了抑郁症？",
        )
        history = [
            ChatMessage(role="user", content="之前问过一个学校资源问题。"),
            ChatMessage(role="assistant", content="可以继续问。"),
            ChatMessage(role="user", content="我还想了解更多。"),
        ]
        for message in messages:
            with self.subTest(message=message):
                request = OrchestrationRequest(message=message, history=history)
                rag_needed = await orchestrator._should_retrieve_knowledge(message, history)
                decision = await orchestrator._decide_route(request, rag_needed=rag_needed)
                self.assertEqual(decision["route"], "knowledge_support")

    async def test_follow_up_feedback_runs_effectiveness_and_adjustment_chain(self):
        orchestrator = Orchestrator()
        chat_stub = _ChatStub()
        orchestrator.crisis_agent = _CrisisStub()
        orchestrator.emotion_agent = _MildEmotionStub()
        orchestrator.rag_agent = _RagStub()
        orchestrator.chat_agent = chat_stub
        request = OrchestrationRequest.model_validate({
            "message": "我按上次的呼吸练习做了三天，但还是睡不着。",
            "context": {"user_id": 1, "metadata": {
                "latest_intervention": {"id": 18, "strategy": "睡前呼吸练习"},
                "trend_points": [
                    {"timestamp": "2026-08-10T00:00:00Z", "anxiety": 0.5, "stress": 0.5, "depression": 0.1, "intervention": True},
                    {"timestamp": "2026-08-13T00:00:00Z", "anxiety": 0.8, "stress": 0.8, "depression": 0.2},
                ],
            }},
        })
        result = await orchestrator.run(request)
        self.assertIsNotNone(result.follow_up)
        self.assertEqual(result.follow_up.adherence, "completed")
        self.assertEqual(result.follow_up.effectiveness, "unchanged")
        self.assertEqual(result.follow_up.decision, "replace")
        self.assertIn("follow_up_agent", result.trace)
        self.assertLess(result.trace.index("follow_up_agent"), result.trace.index("profile_agent"))
        self.assertIn("替换", result.intervention.strategy)
        action_titles = [action.title for action in result.intervention.actions]
        self.assertIn("睡前一小时减少刷屏", action_titles)
        self.assertIn("连续三天记录入睡情况", action_titles)
        self.assertNotIn("低负担自我调节", action_titles)

    async def test_high_crisis_cancels_analysis_without_unawaited_coroutines(self):
        orchestrator = Orchestrator()
        orchestrator.crisis_agent = _ImmediateHighCrisisStub()
        orchestrator.emotion_agent = _EmotionStub()
        orchestrator.rag_agent = _RagStub()
        request = OrchestrationRequest(message="我最近心情很差")
        state = orchestrator._initial_state(request)
        state["values"]["safety"] = SafetyDecision(
            decision="allow",
            redacted_message=request.message,
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RuntimeWarning)
            result = await orchestrator._initial_analysis_node(state)
            gc.collect()

        self.assertEqual(result["values"]["crisis"].level, "high")
        self.assertFalse(
            any("was never awaited" in str(item.message) for item in caught),
            [str(item.message) for item in caught],
        )

    async def test_normal_flow_runs_trend_and_risk_before_dialogue(self):
        orchestrator = Orchestrator()
        chat_stub = _ChatStub()
        orchestrator.crisis_agent = _CrisisStub()
        orchestrator.emotion_agent = _EmotionStub()
        orchestrator.rag_agent = _RagStub()
        orchestrator.chat_agent = chat_stub

        request = OrchestrationRequest.model_validate(
            {
                "message": "最近考试压力很大，睡不着",
                "context": {
                    "user_id": 1,
                    "metadata": {
                        "trend_points": [
                            {
                                "timestamp": "2026-07-20T00:00:00Z",
                                "anxiety": 0.3,
                                "stress": 0.3,
                                "depression": 0.1,
                            },
                            {
                                "timestamp": "2026-07-24T00:00:00Z",
                                "anxiety": 0.5,
                                "stress": 0.55,
                                "depression": 0.15,
                            },
                            {
                                "timestamp": "2026-07-28T00:00:00Z",
                                "anxiety": 0.8,
                                "stress": 0.85,
                                "depression": 0.2,
                            },
                        ]
                    },
                },
            }
        )

        result = await orchestrator.run(request)

        self.assertIsNotNone(result.trend)
        self.assertEqual(result.trend.data_points, 3)
        self.assertIsNotNone(result.risk)
        self.assertIs(chat_stub.received_risk, result.risk)
        self.assertIsNotNone(chat_stub.received_intervention)
        self.assertLess(result.trace.index("trend_agent"), result.trace.index("risk_agent"))
        self.assertLess(result.trace.index("risk_agent"), result.trace.index("chat_agent"))
        self.assertIn("trend", result.audit.versions.agent_versions)
        self.assertIn("risk", result.audit.versions.agent_versions)
        self.assertEqual(result.audit.decisions.risk_level, result.risk.risk_level)
        self.assertEqual(result.audit.routing.selected_route, "structured_assessment")
        self.assertEqual(result.audit.routing.policy_version, "risk-constrained-router-1.1.0")
        self.assertTrue(result.audit.routing.features["assessment_evidence"])
        self.assertIn("structured_assessment", result.audit.routing.route_scores)
        initial_analysis = next(
            event for event in result.trace_events if event.agent == "initial_analysis"
        )
        self.assertEqual(
            set(initial_analysis.metadata["subagent_duration_ms"]),
            {"crisis_agent", "rag_intent", "rag_agent", "emotion_agent", "trend_agent"},
        )


if __name__ == "__main__":
    unittest.main()
