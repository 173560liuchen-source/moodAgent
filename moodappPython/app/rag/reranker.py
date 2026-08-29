from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ..config import (
    RERANK_API_BASE_URL,
    RERANK_API_KEY,
    RERANK_INITIAL_MULTIPLIER,
    RERANK_MAX_RETRIES,
    RERANK_MODEL,
    RERANK_TIMEOUT_SECONDS,
    RAG_MAX_CITATIONS_PER_DOCUMENT,
    RAG_RERANK_ACCEPT_THRESHOLD,
    RAG_RERANK_RAW_ACCEPT_THRESHOLD,
    HTTP_KEEPALIVE_EXPIRY_SECONDS,
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
)
from .contracts import RerankItem, RerankSummary, RerankTraceItem, RetrievalCitation, RetrievalError, RetrievalSummary
from .retriever import KnowledgeRetrievalService


class RerankGatewayError(RuntimeError):
    pass


class RerankConfigurationError(RerankGatewayError):
    pass


class RerankGateway:
    def __init__(
        self,
        *,
        api_base_url: str = RERANK_API_BASE_URL,
        api_key: str = RERANK_API_KEY,
        model: str = RERANK_MODEL,
        timeout_seconds: float = RERANK_TIMEOUT_SECONDS,
        max_retries: int = RERANK_MAX_RETRIES,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    def ensure_configured(self) -> None:
        if not self.api_base_url:
            raise RerankConfigurationError("RERANK_API_BASE_URL is not configured")
        if not self.api_key:
            raise RerankConfigurationError("RERANK_API_KEY is not configured")
        if not self.model:
            raise RerankConfigurationError("RERANK_MODEL is not configured")

    async def rerank(self, *, query: str, documents: list[str], top_n: int) -> list[RerankItem]:
        self.ensure_configured()
        clean_query = query.strip()
        clean_documents = [document.strip() for document in documents]
        if not clean_query:
            raise RerankGatewayError("Rerank query cannot be empty")
        if not clean_documents:
            return []
        if any(not document for document in clean_documents):
            raise RerankGatewayError("Rerank documents contain empty text")

        payload = {
            "model": self.model,
            "query": clean_query,
            "documents": clean_documents,
            "top_n": min(max(1, top_n), len(clean_documents)),
            "return_documents": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.api_base_url}/rerank"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                data = await self._post(url, headers, payload)
                return self._extract_items(data, expected_count=len(clean_documents))
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                retryable = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))
                if isinstance(exc, httpx.HTTPStatusError):
                    status_code = exc.response.status_code
                    retryable = status_code == 429 or status_code >= 500
                if not retryable or attempt >= self.max_retries:
                    break
                await asyncio.sleep(min(2.0, 0.25 * (2**attempt)))

        raise RerankGatewayError(f"Rerank API call failed: {last_error}") from last_error

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout_seconds),
                    limits=httpx.Limits(
                        max_connections=HTTP_MAX_CONNECTIONS,
                        max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
                        keepalive_expiry=HTTP_KEEPALIVE_EXPIRY_SECONDS,
                    ),
                )
            return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _post(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            response.raise_for_status()
        response.encoding = "utf-8"
        return response.json()

    @staticmethod
    def _extract_items(data: dict[str, Any], *, expected_count: int) -> list[RerankItem]:
        results = data.get("results", data.get("data"))
        if not isinstance(results, list):
            raise ValueError("Rerank response must contain results list")

        items: list[RerankItem] = []
        for row in results:
            index = int(row.get("index"))
            if index < 0 or index >= expected_count:
                raise ValueError(f"Rerank response index out of range: {index}")
            score = row.get("relevance_score", row.get("score"))
            items.append(RerankItem(index=index, relevance_score=float(score)))
        return sorted(items, key=lambda item: item.relevance_score, reverse=True)


class KnowledgeReranker:
    def __init__(self, gateway: RerankGateway | None = None) -> None:
        self.gateway = gateway or RerankGateway()

    async def aclose(self) -> None:
        await self.gateway.aclose()

    async def rerank_citations(
        self,
        *,
        query: str,
        citations: list[RetrievalCitation],
        top_k: int = 5,
    ) -> RerankSummary:
        if not citations:
            return RerankSummary(
                query=query,
                model=self.gateway.model or "unconfigured",
                input_count=0,
                output_count=0,
            )

        try:
            rerank_items = await self.gateway.rerank(
                query=query,
                documents=[citation.content for citation in citations],
                top_n=min(top_k, len(citations)),
            )
            citations_by_index = {index: citation for index, citation in enumerate(citations)}
            raw_scores = {
                item.index: max(0.0, float(item.relevance_score))
                for item in rerank_items
            }
            max_raw_score = max(raw_scores.values(), default=0.0)
            rerank_score_by_index = {
                index: min(1.0, score / max_raw_score) if max_raw_score > 0 else 0.0
                for index, score in raw_scores.items()
            }
            ordered_indexes = [
                item.index
                for item in sorted(
                    rerank_items,
                    key=lambda item: self._final_score(
                        float(citations_by_index[item.index].metadata.get("vector_score") or 0.0),
                        float(citations_by_index[item.index].metadata.get("keyword_score") or 0.0),
                        rerank_score_by_index[item.index],
                    ),
                    reverse=True,
                )
            ][:top_k]

            reranked_citations: list[RetrievalCitation] = []
            trace: list[RerankTraceItem] = []
            for index in ordered_indexes:
                citation = citations_by_index[index]
                rerank_score = rerank_score_by_index[index]
                vector_score = float(citation.metadata.get("vector_score") or 0.0)
                keyword_score = float(citation.metadata.get("keyword_score") or 0.0)
                final_score = self._final_score(vector_score, keyword_score, rerank_score)
                metadata = dict(citation.metadata)
                metadata["rerank_score"] = rerank_score
                metadata["rerank_raw_score"] = raw_scores[index]
                metadata["final_score"] = final_score
                reranked_citations.append(citation.model_copy(update={"score": final_score, "metadata": metadata}))
                trace.append(
                    RerankTraceItem(
                        chunk_id=citation.chunk_id,
                        vector_score=vector_score,
                        keyword_score=keyword_score,
                        rerank_score=rerank_score,
                        final_score=final_score,
                    )
                )

            return RerankSummary(
                query=query,
                model=self.gateway.model or "unconfigured",
                input_count=len(citations),
                output_count=len(reranked_citations),
                citations=reranked_citations,
                trace=trace,
            )
        except Exception as exc:  # noqa: BLE001 - converted to structured rerank error.
            return RerankSummary(
                query=query,
                model=self.gateway.model or "unconfigured",
                input_count=len(citations),
                output_count=0,
                errors=[
                    RetrievalError(
                        error_code=exc.__class__.__name__,
                        message=str(exc),
                    )
                ],
            )

    @staticmethod
    def _final_score(vector_score: float, keyword_score: float, rerank_score: float) -> float:
        return max(
            0.0,
            min(1.0, (0.35 * vector_score) + (0.20 * keyword_score) + (0.45 * rerank_score)),
        )


class RerankedKnowledgeRetrievalService:
    def __init__(
        self,
        *,
        retrieval_service: KnowledgeRetrievalService | None = None,
        reranker: KnowledgeReranker | None = None,
        initial_multiplier: int = RERANK_INITIAL_MULTIPLIER,
    ) -> None:
        self.retrieval_service = retrieval_service or KnowledgeRetrievalService()
        self.reranker = reranker or KnowledgeReranker()
        self.initial_multiplier = max(1, initial_multiplier)

    async def aclose(self) -> None:
        await asyncio.gather(
            self.retrieval_service.aclose(),
            self.reranker.aclose(),
        )

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        min_score: float = 0.2,
        categories: list[str] | None = None,
        child_categories: list[str] | None = None,
        allow_category_fallback: bool = True,
        accept_score: float = RAG_RERANK_ACCEPT_THRESHOLD,
        max_per_document: int = RAG_MAX_CITATIONS_PER_DOCUMENT,
    ) -> RetrievalSummary:
        initial_top_k = min(50, max(top_k, top_k * self.initial_multiplier))
        retrieval_kwargs = {
            "top_k": initial_top_k,
            "min_score": min_score,
            "categories": categories,
        }
        # 保持旧测试桩与第三方检索服务兼容；仅分层调用才传递新增参数。
        if child_categories is not None or not allow_category_fallback:
            retrieval_kwargs["child_categories"] = child_categories
            retrieval_kwargs["allow_category_fallback"] = allow_category_fallback
        initial = await self.retrieval_service.search(query, **retrieval_kwargs)
        if initial.errors or not initial.citations:
            return initial

        reranked = await self.reranker.rerank_citations(
            query=query,
            citations=initial.citations,
            top_k=top_k,
        )
        if reranked.errors:
            fallback = self._diversify(initial.citations, top_k, max_per_document)
            fallback = await self._expand_parent_contexts(fallback)
            fallback = self._diversify(fallback, top_k, max_per_document)
            return initial.model_copy(update={
                "top_k": top_k,
                "result_count": len(fallback),
                "has_evidence": bool(fallback),
                "no_evidence_reason": None if fallback else "no_relevant_chunks",
                "citations": fallback,
                "warnings": initial.warnings + reranked.errors,
                "retrieval_strategy": "hybrid_fallback" if initial.retrieval_strategy == "hybrid_fallback" else initial.retrieval_strategy,
            })

        accepted = [
            citation for citation in reranked.citations
            if citation.score >= accept_score
            and float(citation.metadata.get("rerank_raw_score") or 0.0) >= RAG_RERANK_RAW_ACCEPT_THRESHOLD
        ]
        accepted = self._diversify(accepted, top_k, max_per_document)
        accepted = await self._expand_parent_contexts(accepted)
        accepted = self._diversify(accepted, top_k, max_per_document)

        return RetrievalSummary(
            query=initial.query,
            top_k=top_k,
            min_score=min_score,
            result_count=len(accepted),
            has_evidence=bool(accepted),
            no_evidence_reason=None if accepted else "no_relevant_chunks",
            citations=accepted,
            warnings=initial.warnings,
            retrieval_strategy="hybrid_reranked",
            category_fallback_used=initial.category_fallback_used,
            category_candidate_counts=initial.category_candidate_counts,
            candidate_count=initial.candidate_count,
        )

    async def _expand_parent_contexts(
        self,
        citations: list[RetrievalCitation],
    ) -> list[RetrievalCitation]:
        expand = getattr(self.retrieval_service, "expand_parent_contexts", None)
        if not callable(expand):
            return citations
        return await expand(citations)

    @staticmethod
    def _diversify(citations: list[RetrievalCitation], top_k: int, max_per_document: int) -> list[RetrievalCitation]:
        result: list[RetrievalCitation] = []
        counts: dict[str, int] = {}
        for citation in sorted(citations, key=lambda item: item.score, reverse=True):
            if counts.get(citation.document_id, 0) >= max(1, max_per_document):
                continue
            result.append(citation)
            counts[citation.document_id] = counts.get(citation.document_id, 0) + 1
            if len(result) >= top_k:
                break
        return result
