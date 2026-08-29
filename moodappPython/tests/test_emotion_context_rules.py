import asyncio
import unittest

from app.agents.emotion_agent import EmotionAgent
from app.evaluation.fault_injection import TimeoutModelGateway
from app.schemas import ChatMessage


class EmotionContextRulesTest(unittest.TestCase):
    def test_degree_words_change_intensity(self):
        weak = EmotionAgent._fast_analysis("我有点焦虑")
        strong = EmotionAgent._fast_analysis("我非常焦虑")
        self.assertIsNotNone(weak)
        self.assertIsNotNone(strong)
        self.assertEqual(weak.emotion, "anxious")
        self.assertEqual(strong.emotion, "anxious")
        self.assertGreater(strong.anxiety, weak.anxiety)

    def test_negated_emotion_is_not_scored_as_active(self):
        result = EmotionAgent._fast_analysis("我现在没有焦虑，也不再难过")
        self.assertIsNotNone(result)
        self.assertEqual(result.emotion, "calm")
        self.assertEqual(result.anxiety, 0.0)
        self.assertEqual(result.depression, 0.0)

    def test_implicit_expressions_are_detected(self):
        sad = EmotionAgent._fast_analysis("我最近什么都不想做")
        lonely = EmotionAgent._fast_analysis("我觉得没人理解我")
        stressed = EmotionAgent._fast_analysis("我最近总是喘不过气")
        self.assertEqual(sad.emotion, "sad")
        self.assertEqual(lonely.emotion, "lonely")
        self.assertEqual(stressed.emotion, "stressed")

    def test_time_management_pressure_is_detected_without_model(self):
        result = EmotionAgent._fast_analysis(
            "我每天都在赶ddl，越想安排时间越乱，感觉自己效率特别低。"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.emotion, "stressed")
        self.assertGreater(result.stress, 0)

    def test_reluctance_to_tell_parents_about_pressure_is_user_stress(self):
        result = EmotionAgent._fast_analysis(
            "我不太敢和父母说压力，但我有一个关系还不错的辅导员。"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.emotion, "stressed")
        self.assertIn("压力", result.evidence)

    def test_neutral_counselor_information_does_not_create_emotion(self):
        result = EmotionAgent._fast_analysis("我想了解辅导员的值班时间。")

        self.assertIsNone(result)

    def test_third_person_emotion_is_not_assigned_to_user(self):
        result = EmotionAgent._fast_analysis("我朋友最近很难过，也非常焦虑")
        self.assertIsNone(result)

    def test_later_first_person_emotion_is_not_hidden_by_earlier_third_person(self):
        result = EmotionAgent._fast_analysis(
            "班里有人一直威胁我，不让我告诉老师，我每天都很害怕。"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.emotion, "fearful")
        self.assertGreater(result.confidence, 0)
        self.assertIn("害怕", result.evidence)

    def test_reported_third_person_fear_remains_excluded(self):
        result = EmotionAgent._fast_analysis(
            "朋友说他每天都很害怕，也不敢告诉老师。"
        )

        self.assertIsNone(result)

    def test_only_recent_user_turns_affect_context(self):
        history = [
            ChatMessage(role="user", content="我很焦虑"),
            ChatMessage(role="assistant", content="你非常绝望，也很孤独"),
            ChatMessage(role="user", content="我今天平静多了"),
        ]
        result = EmotionAgent._fast_analysis("我现在感觉好多了", history)
        self.assertIsNotNone(result)
        self.assertEqual(result.emotion, "calm")
        self.assertEqual(result.loneliness, 0.0)

    def test_context_is_limited_to_five_user_turns(self):
        history = [
            ChatMessage(role="user", content="我很焦虑"),
            ChatMessage(role="user", content="普通记录一"),
            ChatMessage(role="user", content="普通记录二"),
            ChatMessage(role="user", content="普通记录三"),
            ChatMessage(role="user", content="普通记录四"),
            ChatMessage(role="user", content="我最近一直很孤独"),
        ]
        result = EmotionAgent._fast_analysis("我现在也觉得没人理解我", history)
        self.assertIsNotNone(result)
        self.assertEqual(result.emotion, "lonely")
        self.assertEqual(result.anxiety, 0.0)


class EmotionTimeoutFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_time_management_pressure_enters_fast_path_before_model(self):
        result = await EmotionAgent(TimeoutModelGateway()).analyze(
            "我每天都在赶ddl，越想安排时间越乱，感觉自己效率特别低。"
        )

        self.assertEqual(result.emotion, "stressed")
        self.assertEqual(result.parse_status, "ok")
        self.assertIn("deterministic_fast_path", result.validation_warnings)

    async def test_timeout_uses_extended_local_rules(self):
        result = await EmotionAgent(TimeoutModelGateway()).analyze("我最近一直提不起劲，觉得自己很没用")
        self.assertEqual(result.emotion, "sad")
        self.assertGreater(result.depression, 0)
        self.assertGreater(result.confidence, 0)
        self.assertLessEqual(result.confidence, 0.55)
        self.assertFalse(result.insufficient_data)
        self.assertEqual(result.parse_status, "fallback")
        self.assertIn("local_rule_fallback", result.validation_warnings)
        self.assertTrue(result.evidence)

    async def test_timeout_does_not_assign_third_person_emotion_to_user(self):
        result = await EmotionAgent(TimeoutModelGateway()).analyze("我朋友最近一直提不起劲，也觉得自己很没用")
        self.assertEqual(result.emotion, "unknown")
        self.assertTrue(result.insufficient_data)
        self.assertEqual(result.confidence, 0.0)

    async def test_timeout_without_emotion_signal_remains_unknown(self):
        result = await EmotionAgent(TimeoutModelGateway()).analyze("今天下午有一节课")
        self.assertEqual(result.emotion, "unknown")
        self.assertTrue(result.insufficient_data)

    async def test_timeout_fallback_uses_recent_user_context_only(self):
        history = [
            ChatMessage(role="assistant", content="你最近很孤独，也很焦虑"),
            ChatMessage(role="user", content="我这几天一直提不起劲"),
        ]
        result = await EmotionAgent(TimeoutModelGateway()).analyze("今天还是觉得很没用", history)
        self.assertEqual(result.emotion, "sad")
        self.assertEqual(result.loneliness, 0.0)
        self.assertGreater(result.depression, 0)


if __name__ == "__main__":
    unittest.main()
