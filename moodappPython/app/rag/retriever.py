from __future__ import annotations

import asyncio
import json
import re
from collections import Counter

from .contracts import KNOWLEDGE_CATEGORIES, RetrievalCitation, RetrievalError, RetrievalSummary
from .embedding_gateway import EmbeddingGateway
from .vector_store import PgVectorKnowledgeStore


class KnowledgeRetrievalError(RuntimeError):
    pass


class PgVectorKnowledgeRetriever:
    def __init__(self, vector_store: PgVectorKnowledgeStore | None = None) -> None:
        self.vector_store = vector_store or PgVectorKnowledgeStore()

    def search_by_vector(
        self,
        *,
        query_embedding: list[float],
        top_k: int = 20,
        min_score: float = 0.15,
        categories: list[str] | None = None,
        child_categories: list[str] | None = None,
    ) -> list[RetrievalCitation]:
        self._validate(query_embedding=query_embedding, top_k=top_k, min_score=min_score, categories=categories)
        query_vector = PgVectorKnowledgeStore._vector_literal(query_embedding)
        params: list[object] = [query_vector, query_vector, min_score]
        where_clauses = [
            "(1 - (embedding <=> %s::vector)) >= %s",
            "COALESCE(metadata ->> 'chunk_level', 'child') = 'child'",
        ]
        if categories:
            placeholders = ", ".join(["%s"] * len(categories))
            where_clauses.append(f"category IN ({placeholders})")
            params.extend(categories)
        if child_categories:
            placeholders = ", ".join(["%s"] * len(child_categories))
            where_clauses.append(f"metadata -> 'child_categories' ?| ARRAY[{placeholders}]")
            params.extend(child_categories)
        params.extend([query_vector, top_k])
        sql = f"""
            SELECT source, document_id, category, chunk_id, content, file_path,
                   file_name, file_type, content_hash, document_hash, char_start,
                   char_end, heading_path, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM {self.vector_store.config.full_table_name}
            WHERE {" AND ".join(where_clauses)}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self.vector_store._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [self._citation(row, float(row[14]), "vector") for row in cur.fetchall()]

    def search_by_keyword(
        self,
        *,
        query: str,
        top_k: int = 20,
        categories: list[str] | None = None,
        child_categories: list[str] | None = None,
    ) -> list[RetrievalCitation]:
        terms = self.keyword_terms(query)
        if not terms:
            return []
        clauses: list[str] = []
        params: list[object] = []
        for term in terms:
            clauses.append("(content ILIKE %s OR source ILIKE %s OR file_name ILIKE %s)")
            pattern = f"%{term}%"
            params.extend([pattern, pattern, pattern])
        where = [
            "(" + " OR ".join(clauses) + ")",
            "COALESCE(metadata ->> 'chunk_level', 'child') = 'child'",
        ]
        if categories:
            unknown = sorted(set(categories) - set(KNOWLEDGE_CATEGORIES))
            if unknown:
                raise KnowledgeRetrievalError("Unknown knowledge categories: " + ", ".join(unknown))
            placeholders = ", ".join(["%s"] * len(categories))
            where.append(f"category IN ({placeholders})")
            params.extend(categories)
        if child_categories:
            placeholders = ", ".join(["%s"] * len(child_categories))
            where.append(f"metadata -> 'child_categories' ?| ARRAY[{placeholders}]")
            params.extend(child_categories)
        params.append(min(100, max(top_k, top_k * 4)))
        sql = f"""
            SELECT source, document_id, category, chunk_id, content, file_path,
                   file_name, file_type, content_hash, document_hash, char_start,
                   char_end, heading_path, metadata
            FROM {self.vector_store.config.full_table_name}
            WHERE {" AND ".join(where)}
            LIMIT %s
        """
        with self.vector_store._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        scored: list[RetrievalCitation] = []
        for row in rows:
            searchable = f"{row[0]} {row[4]} {row[6]}".lower()
            matched = [term for term in terms if term.lower() in searchable]
            coverage = len(matched) / max(1, len(terms))
            title_hits = sum(1 for term in matched if term.lower() in f"{row[0]} {row[6]}".lower())
            score = min(1.0, 0.35 + 0.55 * coverage + min(0.1, title_hits * 0.05))
            citation = self._citation(row, score, "keyword")
            citation.metadata["keyword_terms"] = matched
            scored.append(citation)
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]

    @staticmethod
    def keyword_terms(query: str) -> list[str]:
        vocabulary = (
            "入睡困难", "睡不着", "夜醒", "早醒", "失眠", "睡眠", "昼夜颠倒", "熬夜",
            "学习压力", "压力", "考试", "考研", "绩点", "论文", "实习", "就业", "家庭期待",
            "焦虑", "紧张", "情绪", "孤独", "人际", "宿舍矛盾", "社交焦虑", "被排斥",
            "心理中心", "心理老师", "预约咨询", "辅导员", "校医院", "热线", "求助",
            "自伤", "自杀", "轻生", "危机", "告别", "无望", "伤害他人", "SDS", "SAS",
        )
        terms = [term for term in vocabulary if term.lower() in query.lower()]
        terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,15}", query))
        return list(dict.fromkeys(terms))[:12]

    @staticmethod
    def _validate(*, query_embedding: list[float], top_k: int, min_score: float, categories: list[str] | None) -> None:
        if not query_embedding:
            raise KnowledgeRetrievalError("query_embedding cannot be empty")
        if top_k < 1 or top_k > 50:
            raise KnowledgeRetrievalError("top_k must be between 1 and 50")
        if not 0.0 <= min_score <= 1.0:
            raise KnowledgeRetrievalError("min_score must be between 0 and 1")
        if categories:
            unknown = sorted(set(categories) - set(KNOWLEDGE_CATEGORIES))
            if unknown:
                raise KnowledgeRetrievalError("Unknown knowledge categories: " + ", ".join(unknown))

    @classmethod
    def _citation(cls, row: tuple[object, ...], score: float, source_kind: str) -> RetrievalCitation:
        metadata = cls._json_dict(row[13])
        metadata[f"{source_kind}_score"] = max(0.0, min(1.0, score))
        return RetrievalCitation(
            source=str(row[0]), document_id=str(row[1]), category=str(row[2]),  # type: ignore[arg-type]
            chunk_id=str(row[3]), content=str(row[4]), file_path=str(row[5]),
            chunk_level=str(metadata.get("chunk_level") or "child"),  # type: ignore[arg-type]
            parent_chunk_id=cls._optional_text(metadata.get("parent_chunk_id")),
            file_name=str(row[6]), file_type=str(row[7]), content_hash=str(row[8]),
            document_hash=str(row[9]), char_start=int(row[10]), char_end=int(row[11]),
            heading_path=cls._json_list(row[12]), metadata=metadata,
            title=cls._optional_text(metadata.get("title")) or str(row[0]),
            publisher=cls._optional_text(metadata.get("publisher")),
            source_url=cls._optional_text(metadata.get("source_url")),
            document_version=cls._optional_text(metadata.get("document_version")),
            reviewed_at=metadata.get("reviewed_at"),
            score=max(0.0, min(1.0, score)),
        )

    def fetch_parent_chunks(self, parent_chunk_ids: list[str]) -> list[RetrievalCitation]:
        """Load parent contexts after child retrieval; parent rows are never vector candidates."""
        unique_ids = list(dict.fromkeys(item for item in parent_chunk_ids if item))
        if not unique_ids:
            return []
        sql = f"""
            SELECT source, document_id, category, chunk_id, content, file_path,
                   file_name, file_type, content_hash, document_hash, char_start,
                   char_end, heading_path, metadata
            FROM {self.vector_store.config.full_table_name}
            WHERE chunk_id = ANY(%s)
              AND metadata ->> 'chunk_level' = 'parent'
        """
        with self.vector_store._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (unique_ids,))
                return [self._citation(row, 0.0, "parent") for row in cur.fetchall()]

    @staticmethod
    def _optional_text(value: object) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _json_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return [str(item) for item in parsed] if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def _json_dict(value: object) -> dict[str, object]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


class KnowledgeRetrievalService:
    def __init__(
        self,
        *,
        embedding_gateway: EmbeddingGateway | None = None,
        retriever: PgVectorKnowledgeRetriever | None = None,
    ) -> None:
        self.embedding_gateway = embedding_gateway or EmbeddingGateway()
        self.retriever = retriever or PgVectorKnowledgeRetriever()

    async def aclose(self) -> None:
        close = getattr(self.embedding_gateway, "aclose", None)
        if close is not None:
            await close()

    async def expand_parent_contexts(
        self,
        citations: list[RetrievalCitation],
    ) -> list[RetrievalCitation]:
        """Group child hits by parent and replace them with complete parent contexts."""
        parent_ids = [
            citation.parent_chunk_id
            for citation in citations
            if citation.chunk_level == "child" and citation.parent_chunk_id
        ]
        if not parent_ids:
            return citations
        fetch = getattr(self.retriever, "fetch_parent_chunks", None)
        if not callable(fetch):
            return citations
        try:
            parents = await asyncio.to_thread(fetch, parent_ids)
        except Exception:
            # Parent expansion is an enrichment step. A missing parent row must
            # degrade to the already validated child evidence, not erase it.
            return citations

        parents_by_id = {parent.chunk_id: parent for parent in parents}
        children_by_parent: dict[str, list[RetrievalCitation]] = {}
        unexpanded: list[RetrievalCitation] = []
        for citation in citations:
            parent_id = citation.parent_chunk_id
            if citation.chunk_level == "child" and parent_id in parents_by_id:
                children_by_parent.setdefault(parent_id, []).append(citation)
            else:
                unexpanded.append(citation)

        expanded: list[RetrievalCitation] = []
        for parent_id, children in children_by_parent.items():
            ordered_children = sorted(children, key=lambda item: item.score, reverse=True)
            best_child = ordered_children[0]
            parent = parents_by_id[parent_id]
            metadata = dict(parent.metadata)
            metadata.update({
                "retrieval_level": "parent_expanded",
                "matched_child_chunk_ids": [item.chunk_id for item in ordered_children],
                "matched_child_scores": [round(item.score, 6) for item in ordered_children],
                "best_child_chunk_id": best_child.chunk_id,
                "vector_score": best_child.metadata.get("vector_score", 0.0),
                "keyword_score": best_child.metadata.get("keyword_score", 0.0),
                "rerank_score": best_child.metadata.get("rerank_score", 0.0),
                "rerank_raw_score": best_child.metadata.get("rerank_raw_score", 0.0),
                "final_score": best_child.score,
            })
            expanded.append(parent.model_copy(update={
                "score": best_child.score,
                "metadata": metadata,
            }))
        return sorted(expanded + unexpanded, key=lambda item: item.score, reverse=True)

    async def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        min_score: float = 0.15,
        categories: list[str] | None = None,
        child_categories: list[str] | None = None,
        allow_category_fallback: bool = True,
    ) -> RetrievalSummary:
        clean_query = query.strip()
        if not clean_query:
            return RetrievalSummary(
                query=query or "empty", top_k=top_k, min_score=min_score,
                result_count=0, has_evidence=False, no_evidence_reason="empty_query",
                errors=[RetrievalError(error_code="EmptyQuery", message="Query cannot be empty")],
            )

        vector: list[RetrievalCitation] = []
        keyword: list[RetrievalCitation] = []
        warnings: list[RetrievalError] = []
        query_embedding: list[float] | None = None

        async def vector_search() -> tuple[list[float], list[RetrievalCitation]]:
            embedding = (await self.embedding_gateway.embed_texts([clean_query]))[0]
            matches = await asyncio.to_thread(
                self.retriever.search_by_vector,
                query_embedding=embedding, top_k=top_k, min_score=min_score,
                categories=categories, child_categories=child_categories,
            )
            return embedding, matches

        async def keyword_search() -> list[RetrievalCitation]:
            return await asyncio.to_thread(
                self.retriever.search_by_keyword,
                query=clean_query, top_k=top_k, categories=categories, child_categories=child_categories,
            )

        vector_result, keyword_result = await asyncio.gather(
            vector_search(), keyword_search(), return_exceptions=True
        )
        if isinstance(vector_result, BaseException):
            warnings.append(RetrievalError(
                error_code=vector_result.__class__.__name__, message=str(vector_result)
            ))
        else:
            query_embedding, vector = vector_result
        if isinstance(keyword_result, BaseException):
            warnings.append(RetrievalError(
                error_code=keyword_result.__class__.__name__, message=str(keyword_result)
            ))
        else:
            keyword = keyword_result

        merged = self._merge(vector, keyword, top_k)
        fallback_used = False
        if allow_category_fallback and categories and (not merged or merged[0].score < max(min_score, 0.25)):
            fallback_used = True
            fallback_tasks = [asyncio.to_thread(
                self.retriever.search_by_keyword,
                query=clean_query, top_k=top_k, categories=None,
            )]
            if query_embedding:
                fallback_tasks.append(asyncio.to_thread(
                    self.retriever.search_by_vector,
                    query_embedding=query_embedding, top_k=top_k,
                    min_score=min_score, categories=None,
                ))
            fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
            fallback_keyword: list[RetrievalCitation] = []
            fallback_vector: list[RetrievalCitation] = []
            for index, fallback_result in enumerate(fallback_results):
                if isinstance(fallback_result, BaseException):
                    warnings.append(RetrievalError(
                        error_code=fallback_result.__class__.__name__, message=str(fallback_result)
                    ))
                elif index == 0:
                    fallback_keyword = fallback_result
                else:
                    fallback_vector = fallback_result
            merged = self._merge(vector + fallback_vector, keyword + fallback_keyword, top_k)

        strategy = self._strategy(vector, keyword)
        counts = dict(Counter(citation.category for citation in merged))
        fatal_errors = warnings if not merged and warnings else []
        return RetrievalSummary(
            query=clean_query, top_k=top_k, min_score=min_score,
            result_count=len(merged), has_evidence=bool(merged),
            no_evidence_reason=None if merged else ("retrieval_error" if fatal_errors else "no_relevant_chunks"),
            citations=merged, errors=fatal_errors, warnings=[] if fatal_errors else warnings,
            retrieval_strategy=strategy, category_fallback_used=fallback_used,
            category_candidate_counts=counts, candidate_count=len(merged),
        )

    @staticmethod
    def _merge(
        vector: list[RetrievalCitation],
        keyword: list[RetrievalCitation],
        top_k: int,
    ) -> list[RetrievalCitation]:
        by_id: dict[str, RetrievalCitation] = {}
        components: dict[str, dict[str, float]] = {}
        for citation in vector:
            by_id[citation.chunk_id] = citation
            components.setdefault(citation.chunk_id, {})["vector_score"] = citation.score
        for citation in keyword:
            by_id.setdefault(citation.chunk_id, citation)
            components.setdefault(citation.chunk_id, {})["keyword_score"] = citation.score
        merged: list[RetrievalCitation] = []
        for chunk_id, citation in by_id.items():
            scores = components[chunk_id]
            vector_score = scores.get("vector_score", 0.0)
            keyword_score = scores.get("keyword_score", 0.0)
            if vector_score and keyword_score:
                final = 0.65 * vector_score + 0.35 * keyword_score
            elif vector_score:
                final = vector_score
            else:
                final = keyword_score
            metadata = dict(citation.metadata)
            metadata.update(scores)
            merged.append(citation.model_copy(update={"score": round(final, 6), "metadata": metadata}))
        return sorted(merged, key=lambda item: item.score, reverse=True)[:top_k]

    @staticmethod
    def _strategy(vector: list[RetrievalCitation], keyword: list[RetrievalCitation]) -> str:
        if vector and keyword:
            return "hybrid_fallback"
        if vector:
            return "vector_only"
        if keyword:
            return "keyword_only"
        return "hybrid_fallback"
