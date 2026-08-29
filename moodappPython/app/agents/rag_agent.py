from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..rag.contracts import (
    KNOWLEDGE_CATEGORIES,
    KnowledgeCategory,
    RetrievalCitation,
    RetrievalError,
)
from ..rag.reranker import RerankedKnowledgeRetrievalService
from ..rag.hierarchy_classifier import HierarchyClassification, KnowledgeHierarchyClassifier
from ..schemas import ChatMessage
from ..config import (
    RAG_CACHE_MAX_ENTRIES,
    RAG_CACHE_TTL_SECONDS,
    RAG_REQUEST_TIMEOUT_SECONDS,
    RAG_RERANK_ACCEPT_THRESHOLD,
    RAG_VECTOR_CANDIDATE_THRESHOLD,
)


class RAGAnalysis(BaseModel):
    """RAGAgent 的结构化输出。

    该模型只包含知识库检索结果和溯源信息，不保存完整用户聊天记录。
    """

    model_config = ConfigDict(extra="forbid")

    agent: str = "rag"
    query: str = Field(min_length=1)
    rewritten_query: str = Field(min_length=1)
    selected_categories: list[KnowledgeCategory] = Field(default_factory=list)
    hierarchy: HierarchyClassification | None = None
    retrieval_stages: list[dict[str, object]] = Field(default_factory=list)
    top_k: int = Field(ge=1, le=20)
    min_score: float = Field(ge=0.0, le=1.0)
    has_evidence: bool
    no_evidence_reason: Literal[
        "not_applicable",
        "no_relevant_chunks",
        "retrieval_error",
        "empty_query",
    ] | None = None
    citations: list[RetrievalCitation] = Field(default_factory=list)
    errors: list[RetrievalError] = Field(default_factory=list)
    warnings: list[RetrievalError] = Field(default_factory=list)
    retrieval_strategy: Literal[
        "hybrid_reranked",
        "hybrid_fallback",
        "vector_only",
        "keyword_only",
        "skipped",
    ] = "hybrid_reranked"
    category_fallback_used: bool = False
    category_candidate_counts: dict[str, int] = Field(default_factory=dict)
    candidate_count: int = Field(default=0, ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_policy: str = "only_return_real_retrieved_citations"
    prompt_version: str = "rag-agent-6.2.0"
    cache_hit: bool = False


class RAGAgent:
    """本地知识库检索智能体。

    职责边界：
    - 只检索本地知识库，不生成心理建议；
    - 不保存完整用户聊天；
    - 没有资料时明确返回无依据；
    - 返回的每条引用必须来自向量库中的真实 chunk。
    """

    name = "rag"
    version = "6.2.0"

    def __init__(
        self,
        retrieval_service: RerankedKnowledgeRetrievalService | None = None,
        *,
        default_top_k: int = 5,
        default_min_score: float = RAG_VECTOR_CANDIDATE_THRESHOLD,
        default_accept_score: float = RAG_RERANK_ACCEPT_THRESHOLD,
    ) -> None:
        self.retrieval_service = retrieval_service or RerankedKnowledgeRetrievalService()
        self.default_top_k = min(max(1, default_top_k), 20)
        self.default_min_score = max(0.0, min(1.0, default_min_score))
        self.default_accept_score = max(0.0, min(1.0, default_accept_score))
        self.hierarchy_classifier = KnowledgeHierarchyClassifier()
        self._cache: OrderedDict[str, tuple[float, RAGAnalysis]] = OrderedDict()
        self._cache_lock = asyncio.Lock()

    async def _cache_get(self, key: str) -> RAGAnalysis | None:
        if RAG_CACHE_MAX_ENTRIES <= 0 or RAG_CACHE_TTL_SECONDS <= 0:
            return None
        async with self._cache_lock:
            cached = self._cache.get(key)
            if cached is None:
                return None
            expires_at, result = cached
            if expires_at <= time.monotonic():
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return result.model_copy(update={"cache_hit": True}, deep=True)

    async def _cache_put(self, key: str, result: RAGAnalysis) -> None:
        if RAG_CACHE_MAX_ENTRIES <= 0 or RAG_CACHE_TTL_SECONDS <= 0:
            return
        async with self._cache_lock:
            self._cache[key] = (
                time.monotonic() + RAG_CACHE_TTL_SECONDS,
                result.model_copy(deep=True),
            )
            self._cache.move_to_end(key)
            while len(self._cache) > RAG_CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)

    async def aclose(self) -> None:
        close = getattr(self.retrieval_service, "aclose", None)
        if close is not None:
            await close()

    async def retrieve(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
        *,
        top_k: int | None = None,
        min_score: float | None = None,
        hierarchical: bool = True,
        rerank: bool = True,
    ) -> RAGAnalysis:
        query = message.strip()
        if not query:
            return RAGAnalysis(
                query=message or "empty",
                rewritten_query="empty",
                selected_categories=[],
                top_k=top_k or self.default_top_k,
                min_score=min_score if min_score is not None else self.default_min_score,
                has_evidence=False,
                no_evidence_reason="empty_query",
                confidence=0.0,
                retrieval_strategy="skipped",
                errors=[
                    RetrievalError(
                        error_code="EmptyQuery",
                        message="RAG query cannot be empty",
                    )
                ],
            )

        hierarchy = self.hierarchy_classifier.classify(query)
        selected_categories = self._select_categories(query)
        hierarchy_categories = self._parent_to_categories(hierarchy)
        if hierarchy_categories:
            selected_categories = hierarchy_categories
        rewritten_query = self._rewrite_query(query, history)
        safe_top_k = min(max(1, top_k or self.default_top_k), 20)
        safe_min_score = max(0.0, min(1.0, min_score if min_score is not None else self.default_min_score))
        cache_material = (
            rewritten_query,
            tuple(selected_categories), tuple((match.parent_category, tuple(match.child_categories)) for match in hierarchy.matches),
            safe_top_k,
            round(safe_min_score, 6),
            round(self.default_accept_score, 6),
            hierarchical,
            rerank,
        )
        cache_key = hashlib.sha256(repr(cache_material).encode("utf-8")).hexdigest()
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            stages: list[dict[str, object]] = []
            summary, stages = await asyncio.wait_for(
                self._hierarchical_search(
                    rewritten_query, hierarchy=hierarchy, categories=selected_categories,
                    top_k=safe_top_k, min_score=safe_min_score,
                    hierarchical=hierarchical, rerank=rerank,
                ),
                timeout=RAG_REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return RAGAnalysis(
                query=query,
                rewritten_query=rewritten_query,
                selected_categories=selected_categories,
                hierarchy=hierarchy,
                retrieval_stages=stages,
                top_k=safe_top_k,
                min_score=safe_min_score,
                has_evidence=False,
                no_evidence_reason="retrieval_error",
                confidence=0.0,
                retrieval_strategy="hybrid_fallback",
                errors=[RetrievalError(
                    error_code="RAGTimeout",
                    message=f"RAG retrieval exceeded {RAG_REQUEST_TIMEOUT_SECONDS:g}s budget",
                )],
            )
        if summary.errors:
            return RAGAnalysis(
                query=query,
                rewritten_query=rewritten_query,
                selected_categories=selected_categories,
                hierarchy=hierarchy,
                retrieval_stages=stages,
                top_k=safe_top_k,
                min_score=safe_min_score,
                has_evidence=False,
                no_evidence_reason="retrieval_error",
                citations=[],
                errors=summary.errors,
                warnings=summary.warnings,
                confidence=0.0,
                retrieval_strategy="hybrid_fallback",
                category_fallback_used=summary.category_fallback_used,
                category_candidate_counts=summary.category_candidate_counts,
                candidate_count=summary.candidate_count,
            )

        if not summary.citations:
            result = RAGAnalysis(
                query=query,
                rewritten_query=rewritten_query,
                selected_categories=selected_categories,
                hierarchy=hierarchy,
                retrieval_stages=stages,
                top_k=safe_top_k,
                min_score=safe_min_score,
                has_evidence=False,
                no_evidence_reason=summary.no_evidence_reason or "no_relevant_chunks",
                citations=[],
                confidence=0.0,
                warnings=summary.warnings,
                retrieval_strategy=summary.retrieval_strategy,  # type: ignore[arg-type]
                category_fallback_used=summary.category_fallback_used,
                category_candidate_counts=summary.category_candidate_counts,
                candidate_count=summary.candidate_count,
            )
            await self._cache_put(cache_key, result)
            return result

        citations = self._deduplicate_citations(summary.citations)[:safe_top_k]
        result = RAGAnalysis(
            query=query,
            rewritten_query=rewritten_query,
            selected_categories=selected_categories,
            hierarchy=hierarchy,
            retrieval_stages=stages,
            top_k=safe_top_k,
            min_score=safe_min_score,
            has_evidence=bool(citations),
            no_evidence_reason=None if citations else "no_relevant_chunks",
            citations=citations,
            confidence=self._confidence(citations),
            warnings=summary.warnings,
            retrieval_strategy=summary.retrieval_strategy,  # type: ignore[arg-type]
            category_fallback_used=summary.category_fallback_used,
            category_candidate_counts=summary.category_candidate_counts,
            candidate_count=summary.candidate_count,
        )
        await self._cache_put(cache_key, result)
        return result

    @staticmethod
    def _parent_to_categories(hierarchy: HierarchyClassification) -> list[KnowledgeCategory]:
        mapping: dict[str, list[KnowledgeCategory]] = {
            "压力管理": ["stress_management"],
            "睡眠管理": ["sleep_management"],
            "情绪支持": ["student_psychology", "stress_management"],
            "危机干预": ["crisis_guidelines"],
            "校园资源": ["school_resources"],
        }
        result: list[KnowledgeCategory] = []
        for match in hierarchy.matches:
            for category in mapping[match.parent_category]:
                if category not in result:
                    result.append(category)
        return result

    async def _hierarchical_search(
        self,
        query: str,
        *,
        hierarchy: HierarchyClassification,
        categories: list[KnowledgeCategory],
        top_k: int,
        min_score: float,
        hierarchical: bool = True,
        rerank: bool = True,
    ) -> tuple[object, list[dict[str, object]]]:
        stages: list[dict[str, object]] = []
        retrieval_service = self.retrieval_service
        if not rerank:
            retrieval_service = getattr(self.retrieval_service, "retrieval_service", self.retrieval_service)

        async def search_stage(name: str, *, stage_categories: list[KnowledgeCategory] | None, children: list[str] | None, reason: str):
            kwargs = {
                "top_k": top_k, "min_score": min_score, "categories": stage_categories,
                "child_categories": children, "allow_category_fallback": False,
            }
            if retrieval_service is self.retrieval_service:
                kwargs["accept_score"] = self.default_accept_score
            summary = await retrieval_service.search(query, **kwargs)
            stages.append({"stage": name, "reason": reason, "categories": stage_categories or [],
                           "child_categories": children or [], "candidate_count": summary.candidate_count,
                           "result_count": summary.result_count, "top_score": summary.citations[0].score if summary.citations else 0.0})
            return summary

        if not hierarchical:
            summary = await search_stage(
                "global_baseline", stage_categories=None, children=None,
                reason="消融实验：关闭分层检索，直接全知识库检索",
            )
            return summary, stages

        child_categories = [child for match in hierarchy.matches for child in match.child_categories]
        if child_categories and categories:
            summary = await search_stage("child", stage_categories=categories, children=child_categories,
                                         reason="先按识别出的子类精确检索")
            if summary.citations:
                return summary, stages
        if categories:
            summary = await search_stage("parent", stage_categories=categories, children=None,
                                         reason="子类证据不足，回退到父类范围")
            if summary.citations:
                return summary, stages
        summary = await search_stage("global", stage_categories=None, children=None,
                                     reason="父类证据不足或未识别分类，回退全知识库")
        return summary, stages

    @staticmethod
    def _rewrite_query(message: str, history: list[ChatMessage] | None) -> str:
        """确定性查询改写，避免额外模型调用。

        只提取最近少量上下文关键词，不把完整聊天历史送入 RAG。
        """

        history_terms: list[str] = []
        for item in (history or [])[-4:]:
            if item.role == "user":
                history_terms.extend(RAGAgent._domain_terms(item.content))
        unique_background = list(dict.fromkeys(
            term for term in history_terms if term not in message
        ))[:8]
        core = message.strip().replace("\n", " ")[:300]
        if not unique_background:
            return core
        return f"{core}；相关背景：{'、'.join(unique_background)}"[:500]

    @staticmethod
    def _domain_terms(text: str) -> list[str]:
        vocabulary = (
            "入睡困难", "夜醒", "早醒", "失眠", "睡眠", "昼夜颠倒", "熬夜", "补觉", "作息",
            "学习压力", "压力", "考试", "考研", "绩点", "论文", "作业", "实习", "就业",
            "家庭", "父母", "家庭期待", "焦虑", "紧张", "低落", "难过", "沮丧",
            "孤独", "没人理解", "没朋友", "学校", "大学", "高中", "宿舍",
            "宿舍矛盾", "社交焦虑", "被排斥", "心理中心", "心理老师", "预约咨询",
            "辅导员", "校医院", "热线", "校内支持", "求助", "专业帮助", "预约", "满约", "报告",
            "量表", "SAS", "SDS", "思维模式", "自我评价",
            "自伤", "自杀", "轻生", "告别", "无望", "伤害他人",
        )
        return [term for term in vocabulary if term in text]

    @staticmethod
    def _select_categories(message: str) -> list[KnowledgeCategory]:
        text = message.lower()
        categories: list[str] = []
        keyword_map: tuple[tuple[KnowledgeCategory, tuple[str, ...]], ...] = (
            ("crisis_guidelines", ("自杀", "自伤", "自残", "轻生", "伤害自己", "伤害他人", "伤人", "危机", "不想活", "撑不住")),
            ("sleep_management", ("睡不着", "睡不好", "失眠", "睡眠", "入睡", "熬夜", "早醒", "夜醒", "睡不够", "昼夜颠倒", "睡前刷手机", "补觉", "作息")),
            ("stress_management", ("压力", "考试", "学习", "作业", "焦虑", "紧张", "考研", "绩点", "论文", "实习", "就业", "家庭", "父母", "家庭期待", "低落", "难过", "沮丧")),
            ("student_psychology", ("同学", "学校", "大学", "高中", "宿舍", "人际", "孤独", "没人理解", "没朋友", "家庭", "父母", "宿舍矛盾", "社交焦虑", "被排斥", "量表", "sas", "sds", "思维模式", "自我评价")),
            ("school_resources", ("心理中心", "辅导员", "心理老师", "热线", "校医院", "预约咨询", "预约", "满约", "校内支持", "求助", "专业帮助", "哪里可以", "去哪里", "报告", "向学校")),
        )
        for category, keywords in keyword_map:
            if any(keyword in text for keyword in keywords):
                categories.append(category)

        known = set(KNOWLEDGE_CATEGORIES)
        unique: list[KnowledgeCategory] = []
        for category in categories:
            if category in known and category not in unique:
                unique.append(category)  # type: ignore[arg-type]
        return unique

    @staticmethod
    def _deduplicate_citations(citations: list[RetrievalCitation]) -> list[RetrievalCitation]:
        result: list[RetrievalCitation] = []
        seen: set[str] = set()
        for citation in sorted(citations, key=lambda item: item.score, reverse=True):
            if citation.chunk_id in seen:
                continue
            seen.add(citation.chunk_id)
            result.append(citation)
        return result

    @staticmethod
    def _confidence(citations: list[RetrievalCitation]) -> float:
        if not citations:
            return 0.0
        top_score = max(citation.score for citation in citations)
        coverage_bonus = min(0.2, len(citations) * 0.04)
        return round(max(0.0, min(1.0, top_score + coverage_bonus)), 4)
