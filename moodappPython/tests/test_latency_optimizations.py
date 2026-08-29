import asyncio
import threading
import unittest
from unittest.mock import patch

from app.agents.chat_agent import ChatAgent, DialoguePolicyContext
from app.agents.crisis_agent import CrisisAgent
from app.agents.emotion_agent import EmotionAgent
from app.agents.orchestrator import Orchestrator
from app.agents.rag_agent import RAGAgent
from app.model_gateway import ModelGateway
from app.schemas import ModelChatResponse
from app.rag.contracts import RetrievalSummary
from app.rag.retriever import KnowledgeRetrievalService


class _CountingRetrievalService:
    def __init__(self) -> None:
        self.calls = 0

    async def search(
        self,
        query,
        *,
        top_k,
        min_score,
        categories=None,
        child_categories=None,
        allow_category_fallback=True,
        accept_score=0.0,
    ):
        self.calls += 1
        return RetrievalSummary(
            query=query,
            top_k=top_k,
            min_score=min_score,
            result_count=0,
            has_evidence=False,
            no_evidence_reason="no_relevant_chunks",
        )


class _ControlledEmbeddingGateway:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def embed_texts(self, texts):
        self.started.set()
        await self.release.wait()
        return [[0.1, 0.2, 0.3]]


class _ParallelProbeRetriever:
    def __init__(self) -> None:
        self.keyword_started = threading.Event()

    def search_by_keyword(self, **kwargs):
        self.keyword_started.set()
        return []

    def search_by_vector(self, **kwargs):
        return []


class _SlowGateway:
    async def chat(self, request):
        await asyncio.sleep(0.05)
        raise AssertionError("timeout should cancel the slow model call")


class _UnexpectedGateway:
    async def chat(self, request):
        raise AssertionError("deterministic fast path should not call the model")


class _IntentGateway:
    def __init__(self, content="conversation", delay=0.0, error=None):
        self.content = content
        self.delay = delay
        self.error = error
        self.calls = 0

    async def chat(self, request):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return ModelChatResponse(content=self.content, model="intent-test")


class _StreamingGateway:
    model_name = "stream-test"

    def __init__(self, chunks):
        self.chunks = chunks

    async def stream_chat(self, request):
        for chunk in self.chunks:
            yield chunk

    async def chat(self, request):
        return ModelChatResponse(content="".join(self.chunks), model=self.model_name)


class _TruncatedGateway:
    def __init__(self):
        self.max_tokens = None

    async def chat(self, request):
        self.max_tokens = request.max_tokens
        return ModelChatResponse(
            content=(
                "听起来考试临近让你有些焦虑，但你仍能正常上课。"
                "1. 睡前可以放下手机，做几次缓慢呼吸，允许身体"
            ),
            model="truncated-test",
            usage={"finish_reason": "length"},
        )


def _orchestrator_with_intent_gateway(gateway):
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.chat_agent = type("ChatAgentStub", (), {"gateway": gateway})()
    return orchestrator


class LatencyOptimizationTest(unittest.IsolatedAsyncioTestCase):
    def test_low_risk_reply_is_trimmed_at_a_complete_sentence(self):
        body = "".join(
            f"第{index}点建议是先完成一个低负担的小步骤，再观察自己的状态变化。"
            for index in range(1, 12)
        )
        result = ChatAgent._normalize_length(
            body,
            DialoguePolicyContext(),
        )

        self.assertLessEqual(len(result), 320)
        self.assertTrue(result.endswith(("。", "！", "？", "；")))

    async def test_model_gateway_reuses_http_client(self):
        gateway = ModelGateway()
        first = await gateway._get_client()
        second = await gateway._get_client()
        self.assertIs(first, second)
        await gateway.aclose()
        self.assertTrue(first.is_closed)

    async def test_rag_result_cache_avoids_duplicate_retrieval(self):
        service = _CountingRetrievalService()
        agent = RAGAgent(retrieval_service=service)

        first = await agent.retrieve("最近学习压力很大")
        second = await agent.retrieve("最近学习压力很大")

        self.assertFalse(first.has_evidence)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.citations, second.citations)
        # 首次无证据时，父子类分层 RAG 会依次尝试子类、父类和全库；
        # 第二次命中缓存，不应再产生额外检索。
        self.assertEqual(service.calls, 3)

    async def test_rag_routing_skips_plain_disclosure_but_keeps_advice_queries(self):
        gateway = _IntentGateway()
        orchestrator = _orchestrator_with_intent_gateway(gateway)
        self.assertFalse(await orchestrator._should_retrieve_knowledge("最近学习压力比较大。"))
        self.assertTrue(await orchestrator._should_retrieve_knowledge("学习压力大应该怎么办？"))
        self.assertFalse(await orchestrator._should_retrieve_knowledge("学校里没人理解我"))
        self.assertTrue(await orchestrator._should_retrieve_knowledge("学校里没人理解我，可以去哪里求助？"))
        self.assertTrue(await orchestrator._should_retrieve_knowledge("怎么预约学校心理中心？"))
        self.assertTrue(await orchestrator._should_retrieve_knowledge("最近总是睡不着，有什么改善方法？"))
        self.assertTrue(await orchestrator._should_retrieve_knowledge("昼夜颠倒后怎样逐步恢复作息？"))
        self.assertTrue(await orchestrator._should_retrieve_knowledge("SDS量表能不能直接当作抑郁诊断？"))
        self.assertTrue(await orchestrator._should_retrieve_knowledge("你直接告诉我，我是不是已经得了重度抑郁症？"))
        self.assertFalse(await orchestrator._should_retrieve_knowledge("小说里的角色被诊断为抑郁症。"))
        self.assertTrue(await orchestrator._should_retrieve_knowledge("预约心理咨询前需要准备什么？"))
        self.assertFalse(await orchestrator._should_retrieve_knowledge("给我写一段股票短线交易建议。"))
        self.assertTrue(await orchestrator._should_retrieve_knowledge("我有自伤的想法"))
        self.assertFalse(await orchestrator._should_retrieve_knowledge(""))
        self.assertEqual(gateway.calls, 0)

    def test_diagnosis_boundary_rag_rule_requires_user_diagnosis_intent(self):
        self.assertEqual(
            Orchestrator._rule_based_rag_intent("你直接告诉我，我是不是已经得了重度抑郁症？"),
            "retrieve",
        )
        self.assertEqual(
            Orchestrator._rule_based_rag_intent("小说里的角色被诊断为抑郁症。"),
            "conversation",
        )

    async def test_diagnosis_request_always_receives_explicit_non_diagnosis_boundary(self):
        agent = ChatAgent(_IntentGateway(content="根据你之前完成的 SDS 量表，你的指数分为 56。"))
        result = await agent.respond(
            "你直接告诉我，我是不是已经得了重度抑郁症？",
            rag_citations=[{
                "source": "SDS 抑郁自评量表介绍",
                "document_id": "sds-doc",
                "title": "SDS 抑郁自评量表介绍",
                "category": "student_psychology",
                "chunk_id": "sds-chunk-1",
                "content": "自评量表仅用于筛查，不等同于临床诊断。",
                "score": 0.9,
            }],
        )
        self.assertIn("不能替代专业诊断", result.content)
        self.assertIn("不等同于临床诊断", result.content)
        self.assertNotIn("参考资料", result.content)
        self.assertNotIn("SDS 抑郁自评量表介绍", result.content)
        self.assertNotIn("sds-chunk-1", result.content)
        self.assertNotIn("指数分为 56", result.content)
        self.assertNotIn("之前完成", result.content)

    async def test_streaming_rag_reply_keeps_complete_body_without_user_facing_footer(self):
        agent = ChatAgent(_StreamingGateway([
            "预约通常可以通过学校官网、公众号或预约系统查询。",
            "说明当前困扰、持续时间以及对学习生活的影响即可。",
        ]))
        emitted = []
        result = await agent.respond_stream(
            "学校心理中心怎么预约？",
            on_chunk=lambda chunk: self._append_chunk(emitted, chunk),
            rag_citations=[{
                "source": "高校心理支持与校内求助指南",
                "document_id": "school-doc",
                "title": "高校心理支持与校内求助指南",
                "category": "school_resources",
                "chunk_id": "school-chunk-1",
                "content": "可通过学校官网、公众号或预约系统查询，并说明困扰和持续时间。",
                "score": 0.9,
            }],
        )

        self.assertEqual(len(emitted), 1)
        self.assertIn("学校官网、公众号或预约系统", result.content)
        self.assertIn("持续时间", result.content)
        self.assertNotIn("参考资料", result.content)
        self.assertNotIn("高校心理支持与校内求助指南", result.content)
        self.assertNotIn("school-chunk-1", result.content)

    async def test_citation_only_model_output_recovers_contextual_school_answer(self):
        agent = ChatAgent(_IntentGateway(content="参考资料：[1]《高校心理支持与校内求助指南》"))
        result = await agent.respond(
            "如果心理中心暂时预约不上，我还可以联系谁？",
            rag_citations=[{
                "source": "高校心理支持与校内求助指南",
                "document_id": "school-doc",
                "title": "高校心理支持与校内求助指南",
                "category": "school_resources",
                "chunk_id": "school-chunk-1",
                "content": "可联系辅导员、班主任、可信任教师、校医院或宿舍管理人员。",
                "score": 0.9,
            }],
        )

        self.assertIn("辅导员", result.content)
        self.assertNotIn("现在最困扰你的是什么", result.content)
        self.assertNotIn("参考资料", result.content)

    @staticmethod
    async def _append_chunk(target, chunk):
        target.append(chunk)

    async def test_uncertain_rag_intent_uses_lightweight_classifier(self):
        gateway = _IntentGateway(content="retrieve")
        orchestrator = _orchestrator_with_intent_gateway(gateway)
        self.assertEqual(orchestrator._rule_based_rag_intent("这种情况正常吗"), "uncertain")
        self.assertTrue(await orchestrator._should_retrieve_knowledge("这种情况正常吗"))
        self.assertEqual(gateway.calls, 1)

    async def test_uncertain_rag_classifier_can_choose_conversation(self):
        gateway = _IntentGateway(content="conversation")
        orchestrator = _orchestrator_with_intent_gateway(gateway)
        self.assertFalse(await orchestrator._should_retrieve_knowledge("我不知道接下来该说什么"))
        self.assertEqual(gateway.calls, 1)

    async def test_uncertain_rag_classifier_timeout_defaults_to_no_retrieval(self):
        gateway = _IntentGateway(delay=0.05)
        orchestrator = _orchestrator_with_intent_gateway(gateway)
        with patch("app.agents.orchestrator.RAG_INTENT_TIMEOUT_SECONDS", 0.01):
            self.assertFalse(await orchestrator._should_retrieve_knowledge("这种情况正常吗"))

    def test_rag_query_terms_and_categories_cover_expanded_scenarios(self):
        terms = RAGAgent._domain_terms(
            "学校宿舍里没人理解我，父母又催就业，我想预约心理中心"
        )
        self.assertIn("学校", terms)
        self.assertIn("宿舍", terms)
        self.assertIn("没人理解", terms)
        self.assertIn("父母", terms)
        self.assertIn("就业", terms)
        self.assertIn("心理中心", terms)

        categories = RAGAgent._select_categories(
            "学校宿舍里没人理解我，可以去哪里找心理老师求助？"
        )
        self.assertIn("student_psychology", categories)
        self.assertIn("school_resources", categories)

        categories = RAGAgent._select_categories("SAS量表结果应该怎样理解？")
        self.assertIn("student_psychology", categories)
        categories = RAGAgent._select_categories("心理中心满约时还能联系哪些资源？")
        self.assertIn("school_resources", categories)

    async def test_keyword_search_starts_while_embedding_is_in_flight(self):
        embedding = _ControlledEmbeddingGateway()
        retriever = _ParallelProbeRetriever()
        service = KnowledgeRetrievalService(
            embedding_gateway=embedding,
            retriever=retriever,
        )

        search_task = asyncio.create_task(service.search("学习压力", top_k=5))
        await asyncio.wait_for(embedding.started.wait(), timeout=0.2)
        keyword_started = await asyncio.wait_for(
            asyncio.to_thread(retriever.keyword_started.wait, 0.2),
            timeout=0.3,
        )
        self.assertTrue(keyword_started)
        embedding.release.set()
        result = await search_task
        self.assertFalse(result.has_evidence)

    async def test_chat_timeout_returns_safe_fallback(self):
        agent = ChatAgent(_SlowGateway())
        with patch("app.agents.chat_agent.CHAT_REQUEST_TIMEOUT_SECONDS", 0.01):
            result = await agent.respond("最近有点压力")
        self.assertEqual(result.model, "fallback_dialogue")
        self.assertTrue(result.usage["fallback"])

    async def test_exam_anxiety_timeout_returns_contextual_fallback(self):
        agent = ChatAgent(_SlowGateway())
        with patch("app.agents.chat_agent.CHAT_REQUEST_TIMEOUT_SECONDS", 0.01):
            result = await agent.respond("最近考试前有点焦虑，睡眠也不太稳定，但还可以正常上课。")
        self.assertEqual(result.model, "fallback_dialogue")
        self.assertIn("考试临近", result.content)
        self.assertIn("还能正常上课", result.content)
        self.assertNotIn("现在最困扰你的是什么", result.content)

    async def test_length_limited_reply_drops_incomplete_tail_and_closes_cleanly(self):
        gateway = _TruncatedGateway()
        result = await ChatAgent(gateway).respond(
            "最近考试前有点焦虑，睡眠也不太稳定，但还可以正常上课。"
        )

        self.assertGreater(gateway.max_tokens or 0, 280)
        self.assertNotIn("允许身体", result.content)
        self.assertIn("先从其中一个最容易做到的小步骤开始就可以。", result.content)
        self.assertTrue(result.content.endswith("。"))

    async def test_clear_stress_expression_uses_fast_emotion_path(self):
        agent = EmotionAgent(_UnexpectedGateway())
        result = await agent.analyze("最近学习压力较大")
        self.assertEqual(result.emotion, "stressed")
        self.assertGreater(result.stress, 0.7)
        self.assertIn("deterministic_fast_path", result.validation_warnings)

    async def test_clear_academic_stress_uses_low_risk_crisis_fast_path(self):
        agent = CrisisAgent(_UnexpectedGateway())
        result = await agent.assess("最近学习压力较大")
        self.assertEqual(result.level, "low")
        self.assertFalse(result.requires_human_review)
        self.assertIn("deterministic_low_risk_fast_path", result.validation_warnings)

    async def test_mild_exam_anxiety_with_preserved_function_uses_low_risk_fast_path(self):
        agent = CrisisAgent(_UnexpectedGateway())
        result = await agent.assess(
            "最近考试前有点焦虑，睡眠也不太稳定，但还可以正常上课。"
        )
        self.assertEqual(result.level, "low")
        self.assertFalse(result.requires_human_review)
        self.assertIn("deterministic_low_risk_fast_path", result.validation_warnings)

    async def test_clear_depressive_tendency_without_crisis_signal_uses_low_risk_fast_path(self):
        agent = CrisisAgent(_UnexpectedGateway())
        result = await agent.assess(
            "这段时间我对什么都没兴趣，起床也很困难，觉得自己很没用。"
        )

        self.assertEqual(result.level, "low")
        self.assertFalse(result.requires_human_review)
        self.assertIn("deterministic_low_risk_fast_path", result.validation_warnings)

    async def test_diagnosis_question_without_crisis_signal_uses_low_risk_fast_path(self):
        agent = CrisisAgent(_UnexpectedGateway())
        result = await agent.assess("你直接告诉我，我是不是已经得了重度抑郁症？")
        self.assertEqual(result.level, "low")
        self.assertFalse(result.requires_human_review)
        self.assertIn("deterministic_low_risk_fast_path", result.validation_warnings)

    async def test_school_resource_question_uses_low_risk_fast_path(self):
        agent = CrisisAgent(_UnexpectedGateway())
        result = await agent.assess("如果心理中心暂时预约不上，我还可以联系谁？")
        self.assertEqual(result.level, "low")
        self.assertFalse(result.requires_human_review)
        self.assertIn("deterministic_low_risk_fast_path", result.validation_warnings)

    async def test_non_self_crisis_context_stays_low_without_model(self):
        agent = CrisisAgent(_UnexpectedGateway())
        result = await agent.assess("新闻里有人准备了危险工具。")
        self.assertEqual(result.level, "low")
        self.assertFalse(result.requires_human_review)
        self.assertIn("deterministic_non_self_context_fast_path", result.validation_warnings)

    async def test_explicit_high_risk_rule_does_not_wait_for_model(self):
        agent = CrisisAgent(_UnexpectedGateway())
        result = await agent.assess("我已经准备好今晚用药结束生命。")

        self.assertEqual(result.level, "high")
        self.assertEqual(result.action, "crisis_response")
        self.assertTrue(result.hard_rule_triggered)
        self.assertTrue(result.requires_human_review)


if __name__ == "__main__":
    unittest.main()
