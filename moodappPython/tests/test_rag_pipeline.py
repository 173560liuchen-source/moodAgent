import json
import tempfile
import unittest
from pathlib import Path

from app.agents.rag_agent import RAGAgent
from app.evaluation.cases import load_redteam_cases
from app.evaluation.metrics import build_metric_report, evaluate_case_output
from app.evaluation.schemas import RedTeamCase, RedTeamExpectation
from app.rag.chunker import KnowledgeChunker
from app.rag.contracts import RetrievalCitation, RetrievalError, RetrievalSummary
from app.rag.document_parser import KnowledgeDocumentParser
from app.rag.reranker import KnowledgeReranker, RerankedKnowledgeRetrievalService
from app.rag.retriever import KnowledgeRetrievalService
from app.schemas import ChatMessage


def citation(chunk_id: str, document_id: str = "doc-1", *, score: float = 0.8,
             category: str = "stress_management", metadata=None, content=None,
             chunk_level="child", parent_chunk_id=None) -> RetrievalCitation:
    return RetrievalCitation(
        source="压力调节技巧", title="压力调节技巧", document_id=document_id,
        category=category, chunk_id=chunk_id,
        chunk_level=chunk_level, parent_chunk_id=parent_chunk_id,
        content=content or "压力较大时把任务拆成小步骤并练习缓慢呼吸。",
        score=score, file_path="C:/private/knowledge/guide.pdf", file_name="guide.pdf",
        file_type="pdf", content_hash="a" * 64, document_hash="b" * 64,
        char_start=0, char_end=24, metadata=metadata or {},
    )


class FakeEmbedding:
    async def embed_texts(self, texts):
        return [[0.1, 0.2] for _ in texts]


class FallbackRetriever:
    def search_by_vector(self, *, categories=None, **kwargs):
        return [] if categories else [citation("fallback-vector")]

    def search_by_keyword(self, *, categories=None, **kwargs):
        return []


class ParentAwareRetriever:
    def fetch_parent_chunks(self, parent_chunk_ids):
        return [citation(
            "parent-1",
            content="完整父块：先识别压力来源，再把任务拆成小步骤，并说明何时寻求人工支持。",
            chunk_level="parent",
        )] if "parent-1" in parent_chunk_ids else []


class FailingRerankGateway:
    model = "test-reranker"

    async def rerank(self, **kwargs):
        raise TimeoutError("reranker unavailable")


class InitialRetrieval:
    async def search(self, query, *, top_k, min_score, categories=None):
        return RetrievalSummary(
            query=query, top_k=top_k, min_score=min_score, result_count=3,
            has_evidence=True,
            citations=[
                citation("a", "doc-1", score=0.9),
                citation("b", "doc-1", score=0.8),
                citation("c", "doc-2", score=0.7),
            ],
            retrieval_strategy="hybrid_fallback",
        )


class UnavailableRetrieval:
    async def search(self, query, **kwargs):
        return RetrievalSummary(
            query=query, top_k=kwargs["top_k"], min_score=kwargs["min_score"],
            result_count=0, has_evidence=False, no_evidence_reason="retrieval_error",
            errors=[RetrievalError(error_code="RetrieverUnavailable", message="vector store offline")],
        )


class HierarchyRetrieval:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def search(self, query, **kwargs):
        self.calls.append(kwargs)
        citations = self.replies.pop(0)
        return RetrievalSummary(
            query=query, top_k=kwargs["top_k"], min_score=kwargs["min_score"],
            result_count=len(citations), candidate_count=len(citations),
            has_evidence=bool(citations), citations=citations,
            no_evidence_reason=None if citations else "no_relevant_chunks",
        )


class RAGPipelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_hierarchy_search_uses_child_then_parent_fallback(self):
        service = HierarchyRetrieval([[], [citation("parent-hit", category="sleep_management")]])
        agent = RAGAgent(retrieval_service=service)
        result = await agent.retrieve("我最近总是睡不着")
        self.assertEqual([stage["stage"] for stage in result.retrieval_stages], ["child", "parent"])
        self.assertEqual(service.calls[0]["child_categories"], ["入睡困难"])
        self.assertIsNone(service.calls[1]["child_categories"])
        self.assertTrue(result.has_evidence)

    async def test_hierarchy_search_reaches_global_after_parent_miss(self):
        service = HierarchyRetrieval([[], [], [citation("global-hit", category="stress_management")]])
        agent = RAGAgent(retrieval_service=service)
        result = await agent.retrieve("我最近总是睡不着")
        self.assertEqual([stage["stage"] for stage in result.retrieval_stages], ["child", "parent", "global"])
        self.assertIsNone(service.calls[-1]["categories"])
        self.assertTrue(result.has_evidence)

    async def test_ablation_can_switch_to_single_global_search(self):
        service = HierarchyRetrieval([[citation("global-baseline")]])
        result = await RAGAgent(retrieval_service=service).retrieve(
            "我最近总是睡不着", hierarchical=False,
        )
        self.assertEqual([stage["stage"] for stage in result.retrieval_stages], ["global_baseline"])
        self.assertIsNone(service.calls[0]["categories"])
    def test_parser_manifest_and_chunk_provenance(self):
        with tempfile.TemporaryDirectory() as root:
            category = Path(root) / "stress_management"
            category.mkdir()
            document = category / "guide.md"
            document.write_text("# 压力调节\n\n把任务拆成小步骤，并进行呼吸练习。", encoding="utf-8")
            document.with_suffix(".meta.json").write_text(json.dumps({
                "title": "大学生压力调节指南", "publisher": "示例大学心理中心",
                "version": "2026.1", "reviewed_at": "2026-08-01T00:00:00+08:00",
            }, ensure_ascii=False), encoding="utf-8")
            parsed = KnowledgeDocumentParser(root).parse_file(document)
            self.assertEqual(parsed.source, "大学生压力调节指南")
            self.assertEqual(parsed.metadata.publisher, "示例大学心理中心")
            chunks = KnowledgeChunker().chunk_document(parsed)
            self.assertEqual(chunks[0].metadata["document_version"], "2026.1")
            self.assertEqual(chunks[0].metadata["category"], "stress_management")
            self.assertEqual(chunks[0].metadata["source"], "大学生压力调节指南")
            self.assertEqual(chunks[0].metadata["heading_title"], "压力调节")
            self.assertNotIn("聊天", chunks[0].metadata)

    def test_semantic_chunking_keeps_heading_topics_intact(self):
        with tempfile.TemporaryDirectory() as root:
            category = Path(root) / "sleep_management"
            category.mkdir()
            document = category / "sleep.md"
            section_one = "。".join(["固定起床时间有助于稳定睡眠节律"] * 12) + "。"
            section_two = "。".join(["持续失眠并影响白天功能时应寻求专业评估"] * 11) + "。"
            document.write_text(
                "# 学生睡眠指南\n\n适用人群：高校学生\n\n"
                f"## 睡眠卫生\n\n{section_one}\n\n"
                f"## 专业求助\n\n{section_two}",
                encoding="utf-8",
            )
            parsed = KnowledgeDocumentParser(root).parse_file(document)
            chunks = KnowledgeChunker().chunk_document(parsed)

            self.assertGreaterEqual(len(chunks), 2)
            self.assertTrue(all(len(chunk.content) <= 500 for chunk in chunks))
            self.assertTrue(all(chunk.metadata["applicable_audience"] == "高校学生" for chunk in chunks))
            self.assertTrue(any(chunk.heading_path[-1] == "睡眠卫生" for chunk in chunks))
            self.assertTrue(any(chunk.heading_path[-1] == "专业求助" for chunk in chunks))
            self.assertFalse(any("固定起床" in chunk.content and "专业评估" in chunk.content for chunk in chunks))

    def test_parent_child_chunking_links_searchable_children_to_section_parents(self):
        with tempfile.TemporaryDirectory() as root:
            category = Path(root) / "stress_management"
            category.mkdir()
            document = category / "stress.md"
            section = "。".join([
                "考试压力较大时先识别最具体的任务",
                "把任务拆成十分钟内可以完成的小步骤",
                "完成一步后记录实际困难并调整计划",
                "如果持续影响上课和生活应联系学校支持人员",
            ] * 8) + "。"
            document.write_text(f"# 压力指南\n\n## 学业压力\n\n{section}", encoding="utf-8")
            parsed = KnowledgeDocumentParser(root).parse_file(document)
            chunks = KnowledgeChunker().chunk_document(parsed)

            parents = [item for item in chunks if item.chunk_level == "parent"]
            children = [item for item in chunks if item.chunk_level == "child"]
            parent_ids = {item.chunk_id for item in parents}

            self.assertTrue(parents)
            self.assertGreater(len(children), len(parents))
            self.assertTrue(all(item.parent_chunk_id in parent_ids for item in children))
            self.assertTrue(all(item.metadata["chunk_level"] == "child" for item in children))
            self.assertTrue(all(len(item.content) <= 400 for item in children))
            self.assertTrue(any(len(item.content) > 500 for item in parents))

    async def test_child_hits_are_grouped_and_expanded_to_parent_context(self):
        service = KnowledgeRetrievalService(
            embedding_gateway=FakeEmbedding(), retriever=ParentAwareRetriever()
        )
        child_one = citation(
            "child-1", score=0.91, parent_chunk_id="parent-1",
            metadata={"vector_score": 0.8, "rerank_score": 0.9},
        )
        child_two = citation(
            "child-2", score=0.84, parent_chunk_id="parent-1",
            metadata={"keyword_score": 0.7, "rerank_score": 0.8},
        )

        expanded = await service.expand_parent_contexts([child_one, child_two])

        self.assertEqual(len(expanded), 1)
        self.assertEqual(expanded[0].chunk_id, "parent-1")
        self.assertEqual(expanded[0].chunk_level, "parent")
        self.assertEqual(expanded[0].score, 0.91)
        self.assertIn("人工支持", expanded[0].content)
        self.assertEqual(
            expanded[0].metadata["matched_child_chunk_ids"],
            ["child-1", "child-2"],
        )

    def test_pdf_style_headings_and_page_artifacts_are_recognized(self):
        chunker = KnowledgeChunker()
        blocks = chunker._split_into_blocks(
            "心晴 AI · 心理健康知识参考 | 睡眠管理\n"
            "第 1 页\n"
            "1. 常见睡眠困扰\n"
            "• 入睡困难、夜醒或早醒。\n"
            "2. 可执行的睡眠卫生建议\n"
            "1. 固定起床时间，包括周末。\n"
        )

        self.assertFalse(any("第 1 页" in block.text or "心晴 AI" in block.text for block in blocks))
        self.assertEqual(blocks[0].heading_path, ["常见睡眠困扰"])
        self.assertEqual(blocks[-1].heading_path, ["可执行的睡眠卫生建议"])

    def test_structured_query_rewrite_preserves_current_intent(self):
        rewritten = RAGAgent._rewrite_query(
            "现在主要是入睡困难",
            [ChatMessage(role="user", content="前几天因为论文和学习压力很焦虑")],
        )
        self.assertTrue(rewritten.startswith("现在主要是入睡困难"))
        self.assertIn("论文", rewritten)
        self.assertLessEqual(len(rewritten), 500)

    def test_hybrid_merge_keeps_component_scores(self):
        vector = citation("same", score=0.8, metadata={"vector_score": 0.8})
        keyword = citation("same", score=0.6, metadata={"keyword_score": 0.6})
        merged = KnowledgeRetrievalService._merge([vector], [keyword], 5)
        self.assertEqual(len(merged), 1)
        self.assertAlmostEqual(merged[0].score, 0.73)
        self.assertEqual(merged[0].metadata["keyword_score"], 0.6)

    async def test_category_empty_result_falls_back_to_full_library(self):
        service = KnowledgeRetrievalService(
            embedding_gateway=FakeEmbedding(), retriever=FallbackRetriever()
        )
        result = await service.search("睡眠问题", categories=["sleep_management"], top_k=5)
        self.assertTrue(result.has_evidence)
        self.assertTrue(result.category_fallback_used)
        self.assertEqual(result.citations[0].chunk_id, "fallback-vector")

    async def test_rerank_failure_returns_diverse_retrieval_fallback(self):
        service = RerankedKnowledgeRetrievalService(
            retrieval_service=InitialRetrieval(),
            reranker=KnowledgeReranker(FailingRerankGateway()),
        )
        result = await service.search("压力", top_k=2, max_per_document=1)
        self.assertTrue(result.has_evidence)
        self.assertEqual([item.document_id for item in result.citations], ["doc-1", "doc-2"])
        self.assertTrue(result.warnings)
        self.assertEqual(result.retrieval_strategy, "hybrid_fallback")

    async def test_rag_unavailable_degrades_to_auditable_no_evidence_result(self):
        result = await RAGAgent(retrieval_service=UnavailableRetrieval()).retrieve("压力大怎么办")
        self.assertFalse(result.has_evidence)
        self.assertEqual(result.no_evidence_reason, "retrieval_error")
        self.assertEqual(result.errors[0].error_code, "RetrieverUnavailable")
        self.assertEqual(result.retrieval_strategy, "hybrid_fallback")

    def test_sixty_rag_acceptance_cases_and_metrics(self):
        acceptance = [case for case in load_redteam_cases() if "rag_acceptance" in case.tags]
        self.assertEqual(len(acceptance), 60)
        case = RedTeamCase(
            case_id="rag-metric", category="rag_stress", description="metric", message="压力",
            expectation=RedTeamExpectation(
                rag="required", expected_rag_categories=["stress_management"],
                expected_document_ids=["stress_management-"], should_abstain=False,
            ),
        )
        output = {
            "safety": {"decision": "allow"}, "crisis": {"level": "low"},
            "trace": ["safety_gate", "audit_agent"],
            "rag": {"has_evidence": True, "citations": [citation(
                "chunk-1", "stress_management-document-abc"
            ).model_dump(mode="json")]},
            "evaluator": {"final_reply": "把压力任务拆成小步骤。参考 chunk-1", "rag_grounding_score": 0.8},
        }
        result = evaluate_case_output(case, output, latency_ms=10)
        metrics = build_metric_report([case], [result])
        self.assertEqual(metrics.rag_category_recall, 1.0)
        self.assertEqual(metrics.rag_document_recall_at_5, 1.0)
        self.assertEqual(metrics.rag_mrr_at_5, 1.0)


if __name__ == "__main__":
    unittest.main()
