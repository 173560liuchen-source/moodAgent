from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..config import (
    PGVECTOR_SCHEMA,
    PGVECTOR_TABLE,
    POSTGRES_DB,
    POSTGRES_CONNECT_TIMEOUT_SECONDS,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_SSLMODE,
    POSTGRES_USER,
)
from .contracts import (
    ChunkEmbedding,
    KnowledgeChunk,
    VectorStoreError,
    VectorStoreSummary,
    VectorizationSummary,
)


class VectorStoreConfigurationError(RuntimeError):
    pass


class PgVectorStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class PostgresConfig:
    host: str = POSTGRES_HOST
    port: int = POSTGRES_PORT
    dbname: str = POSTGRES_DB
    user: str = POSTGRES_USER
    password: str = POSTGRES_PASSWORD
    sslmode: str = POSTGRES_SSLMODE
    connect_timeout: int = POSTGRES_CONNECT_TIMEOUT_SECONDS
    schema_name: str = PGVECTOR_SCHEMA
    table_name: str = PGVECTOR_TABLE

    def validate(self) -> None:
        missing = [
            name
            for name, value in {
                "POSTGRES_DB": self.dbname,
                "POSTGRES_USER": self.user,
                "POSTGRES_PASSWORD": self.password,
            }.items()
            if not value
        ]
        if missing:
            raise VectorStoreConfigurationError(
                "Missing PostgreSQL config: " + ", ".join(missing)
            )
        if not self.schema_name.replace("_", "").isalnum():
            raise VectorStoreConfigurationError("PGVECTOR_SCHEMA contains invalid characters")
        if not self.table_name.replace("_", "").isalnum():
            raise VectorStoreConfigurationError("PGVECTOR_TABLE contains invalid characters")

    @property
    def full_table_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}"

    def conninfo(self) -> str:
        self.validate()
        return (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.dbname} "
            f"user={self.user} "
            f"password={self.password} "
            f"sslmode={self.sslmode} "
            f"connect_timeout={max(1, int(self.connect_timeout))}"
        )


class PgVectorKnowledgeStore:
    def __init__(self, config: PostgresConfig | None = None) -> None:
        self.config = config or PostgresConfig()
        self.config.validate()

    def setup(self, *, dimensions: int, embedding_model: str | None = None) -> None:
        if dimensions < 1:
            raise PgVectorStoreError("Embedding dimensions must be positive")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.config.schema_name}")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.config.full_table_name} (
                        chunk_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        document_hash TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        heading_path JSONB NOT NULL DEFAULT '[]'::jsonb,
                        ordinal INTEGER NOT NULL,
                        char_start INTEGER NOT NULL,
                        char_end INTEGER NOT NULL,
                        token_count_estimate INTEGER NOT NULL,
                        embedding_model TEXT NOT NULL,
                        embedding vector({dimensions}) NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.config.schema_name}.rag_index_metadata (
                        collection_name TEXT PRIMARY KEY,
                        embedding_model TEXT NOT NULL,
                        dimensions INTEGER NOT NULL,
                        chunker_version TEXT NOT NULL,
                        chunking_config JSONB NOT NULL,
                        knowledge_version TEXT NOT NULL,
                        document_count INTEGER NOT NULL,
                        chunk_count INTEGER NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.config.table_name}_category_idx
                    ON {self.config.full_table_name} (category)
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.config.table_name}_document_id_idx
                    ON {self.config.full_table_name} (document_id)
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.config.table_name}_embedding_ivfflat_idx
                    ON {self.config.full_table_name}
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                    """
                )
            conn.commit()

        self._validate_index_compatibility(dimensions, embedding_model)

    def upsert_chunks(
        self,
        *,
        chunks: list[KnowledgeChunk],
        vector_summary: VectorizationSummary,
    ) -> VectorStoreSummary:
        if vector_summary.dimensions is None:
            return VectorStoreSummary(
                collection_name=self.config.full_table_name,
                persist_directory=self._location(),
                chunk_count=len(chunks),
                upserted_count=0,
                failed_count=len(chunks),
                embedding_model=vector_summary.embedding_model,
                dimensions=None,
                errors=[
                    VectorStoreError(
                        error_code="MissingDimensions",
                        message="Cannot store vectors without embedding dimensions",
                    )
                ],
            )

        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        records: list[tuple[Any, ...]] = []
        errors: list[VectorStoreError] = []

        for vector in vector_summary.vectors:
            chunk = chunk_by_id.get(vector.chunk_id)
            if chunk is None:
                errors.append(
                    VectorStoreError(
                        chunk_id=vector.chunk_id,
                        error_code="ChunkNotFound",
                        message="Vector has no matching knowledge chunk",
                    )
                )
                continue
            if vector.dimensions != vector_summary.dimensions:
                errors.append(
                    VectorStoreError(
                        chunk_id=vector.chunk_id,
                        error_code="DimensionMismatch",
                        message="Vector dimensions do not match vector summary dimensions",
                    )
                )
                continue
            records.append(self._record(chunk, vector))

        try:
            self.setup(
                dimensions=vector_summary.dimensions,
                embedding_model=vector_summary.embedding_model,
            )
            if records:
                self._upsert_records(records)
        except Exception as exc:  # noqa: BLE001 - psycopg and pgvector raise provider-specific errors.
            return VectorStoreSummary(
                collection_name=self.config.full_table_name,
                persist_directory=self._location(),
                chunk_count=len(chunks),
            upserted_count=0,
                deleted_count=0,
                failed_count=len(vector_summary.vectors),
                embedding_model=vector_summary.embedding_model,
                dimensions=vector_summary.dimensions,
                errors=[
                    VectorStoreError(
                        error_code=exc.__class__.__name__,
                        message=str(exc),
                    )
                ],
            )

        return VectorStoreSummary(
            collection_name=self.config.full_table_name,
            persist_directory=self._location(),
            chunk_count=len(chunks),
            upserted_count=len(records),
            deleted_count=0,
            failed_count=len(errors),
            embedding_model=vector_summary.embedding_model,
            dimensions=vector_summary.dimensions,
            errors=errors,
        )

    def sync_chunks(
        self,
        *,
        chunks: list[KnowledgeChunk],
        vector_summary: VectorizationSummary,
        prune_missing: bool = False,
        knowledge_version: str,
        chunking_config: dict[str, Any],
        chunker_version: str,
    ) -> VectorStoreSummary:
        """Atomically upsert a full knowledge snapshot and optionally prune stale chunks."""

        if vector_summary.dimensions is None:
            return VectorStoreSummary(
                collection_name=self.config.full_table_name,
                persist_directory=self._location(),
                chunk_count=len(chunks),
                upserted_count=0,
                failed_count=len(chunks),
                embedding_model=vector_summary.embedding_model,
                dimensions=None,
                errors=[VectorStoreError(error_code="MissingDimensions", message="Missing embedding dimensions")],
            )

        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        records: list[tuple[Any, ...]] = []
        errors: list[VectorStoreError] = []
        for vector in vector_summary.vectors:
            chunk = chunk_by_id.get(vector.chunk_id)
            if chunk is None or vector.dimensions != vector_summary.dimensions:
                errors.append(VectorStoreError(
                    chunk_id=vector.chunk_id,
                    error_code="ChunkOrDimensionMismatch",
                    message="Vector does not match the current chunk snapshot",
                ))
                continue
            records.append(self._record(chunk, vector))

        if errors or len(records) != len(chunks):
            return VectorStoreSummary(
                collection_name=self.config.full_table_name,
                persist_directory=self._location(),
                chunk_count=len(chunks),
                upserted_count=0,
                failed_count=max(len(errors), len(chunks) - len(records)),
                embedding_model=vector_summary.embedding_model,
                dimensions=vector_summary.dimensions,
                errors=errors,
            )

        try:
            self.setup(dimensions=vector_summary.dimensions, embedding_model=vector_summary.embedding_model)
            inserted_count, updated_count, unchanged_count, deleted_count = self._sync_records(
                records,
                active_chunk_ids=list(chunk_by_id),
                prune_missing=prune_missing,
                metadata=(
                    vector_summary.embedding_model,
                    vector_summary.dimensions,
                    chunker_version,
                    json.dumps(chunking_config, ensure_ascii=False),
                    knowledge_version,
                    len({chunk.document_id for chunk in chunks}),
                    len(chunks),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return VectorStoreSummary(
                collection_name=self.config.full_table_name,
                persist_directory=self._location(),
                chunk_count=len(chunks),
                upserted_count=0,
                failed_count=len(chunks),
                embedding_model=vector_summary.embedding_model,
                dimensions=vector_summary.dimensions,
                errors=[VectorStoreError(error_code=exc.__class__.__name__, message=str(exc))],
            )

        return VectorStoreSummary(
            collection_name=self.config.full_table_name,
            persist_directory=self._location(),
            chunk_count=len(chunks),
            upserted_count=len(records),
            inserted_count=inserted_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            deleted_count=deleted_count,
            failed_count=0,
            embedding_model=vector_summary.embedding_model,
            dimensions=vector_summary.dimensions,
        )

    def _validate_index_compatibility(self, dimensions: int, embedding_model: str | None) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT embedding_model, vector_dims(embedding) FROM {self.config.full_table_name} LIMIT 1"
                )
                existing = cur.fetchone()
        if existing and int(existing[1]) != dimensions:
            raise PgVectorStoreError(
                f"Index dimensions {existing[1]} do not match configured dimensions {dimensions}; rebuild required"
            )
        if existing and embedding_model and str(existing[0]) != embedding_model:
            raise PgVectorStoreError(
                f"Index model {existing[0]} does not match configured model {embedding_model}; rebuild required"
            )

    def _sync_records(
        self,
        records: list[tuple[Any, ...]],
        *,
        active_chunk_ids: list[str],
        prune_missing: bool,
        metadata: tuple[Any, ...],
    ) -> tuple[int, int, int, int]:
        inserted_count = 0
        updated_count = 0
        unchanged_count = 0
        deleted_count = 0
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT chunk_id, content_hash, document_id FROM {self.config.full_table_name}"
                )
                existing_rows = cur.fetchall()
                existing_chunks = {str(row[0]): str(row[1]) for row in existing_rows}
                existing_documents = {str(row[2]) for row in existing_rows}
                for record in records:
                    chunk_id, document_id, content_hash = str(record[0]), str(record[1]), str(record[5])
                    if existing_chunks.get(chunk_id) == content_hash:
                        unchanged_count += 1
                    elif chunk_id in existing_chunks or document_id in existing_documents:
                        updated_count += 1
                    else:
                        inserted_count += 1
                self._execute_upsert(cur, records)
                if prune_missing:
                    cur.execute(
                        f"DELETE FROM {self.config.full_table_name} WHERE NOT (chunk_id = ANY(%s))",
                        (active_chunk_ids,),
                    )
                    deleted_count = cur.rowcount
                cur.execute(
                    f"""
                    INSERT INTO {self.config.schema_name}.rag_index_metadata (
                        collection_name, embedding_model, dimensions, chunker_version,
                        chunking_config, knowledge_version, document_count, chunk_count
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                    ON CONFLICT (collection_name) DO UPDATE SET
                        embedding_model=EXCLUDED.embedding_model,
                        dimensions=EXCLUDED.dimensions,
                        chunker_version=EXCLUDED.chunker_version,
                        chunking_config=EXCLUDED.chunking_config,
                        knowledge_version=EXCLUDED.knowledge_version,
                        document_count=EXCLUDED.document_count,
                        chunk_count=EXCLUDED.chunk_count,
                        updated_at=now()
                    """,
                    (self.config.full_table_name, *metadata),
                )
            conn.commit()
        return inserted_count, updated_count, unchanged_count, deleted_count

    def count(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {self.config.full_table_name}")
                value = cur.fetchone()[0]
                return int(value)

    def _upsert_records(self, records: list[tuple[Any, ...]]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._execute_upsert(cur, records)
            conn.commit()

    def _execute_upsert(self, cur: Any, records: list[tuple[Any, ...]]) -> None:
        cur.executemany(
                    f"""
                    INSERT INTO {self.config.full_table_name} (
                        chunk_id,
                        document_id,
                        source,
                        category,
                        content,
                        content_hash,
                        document_hash,
                        file_path,
                        file_name,
                        file_type,
                        heading_path,
                        ordinal,
                        char_start,
                        char_end,
                        token_count_estimate,
                        embedding_model,
                        embedding,
                        metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s, %s, %s, %s, %s, %s::vector, %s::jsonb
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        source = EXCLUDED.source,
                        category = EXCLUDED.category,
                        content = EXCLUDED.content,
                        content_hash = EXCLUDED.content_hash,
                        document_hash = EXCLUDED.document_hash,
                        file_path = EXCLUDED.file_path,
                        file_name = EXCLUDED.file_name,
                        file_type = EXCLUDED.file_type,
                        heading_path = EXCLUDED.heading_path,
                        ordinal = EXCLUDED.ordinal,
                        char_start = EXCLUDED.char_start,
                        char_end = EXCLUDED.char_end,
                        token_count_estimate = EXCLUDED.token_count_estimate,
                        embedding_model = EXCLUDED.embedding_model,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """
                    ,
            records,
        )

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise VectorStoreConfigurationError(
                "Missing dependency psycopg. Install requirements before using pgvector storage."
            ) from exc
        return psycopg.connect(self.config.conninfo())

    def _record(self, chunk: KnowledgeChunk, vector: ChunkEmbedding) -> tuple[Any, ...]:
        return (
            chunk.chunk_id,
            chunk.document_id,
            chunk.source,
            chunk.category,
            chunk.content,
            chunk.content_hash,
            chunk.document_hash,
            str(chunk.metadata.get("file_path") or ""),
            str(chunk.metadata.get("file_name") or ""),
            str(chunk.metadata.get("file_type") or ""),
            json.dumps(chunk.heading_path, ensure_ascii=False),
            chunk.ordinal,
            chunk.char_start,
            chunk.char_end,
            chunk.token_count_estimate,
            vector.embedding_model,
            self._vector_literal(vector.embedding),
            json.dumps(self._metadata(chunk, vector), ensure_ascii=False),
        )

    @staticmethod
    def _vector_literal(embedding: list[float]) -> str:
        return "[" + ",".join(str(float(value)) for value in embedding) + "]"

    @staticmethod
    def _metadata(chunk: KnowledgeChunk, vector: ChunkEmbedding) -> dict[str, Any]:
        return {
            "source": chunk.source,
            "category": chunk.category,
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "chunk_level": chunk.chunk_level,
            "parent_chunk_id": chunk.parent_chunk_id,
            "content_hash": chunk.content_hash,
            "document_hash": chunk.document_hash,
            "embedding_model": vector.embedding_model,
            "dimensions": vector.dimensions,
            "file_path": chunk.metadata.get("file_path") or "",
            "parser": chunk.metadata.get("parser") or "",
            "chunker": chunk.metadata.get("chunker") or "",
            "chunker_version": chunk.metadata.get("chunker_version") or "",
            "title": chunk.metadata.get("title") or chunk.source,
            "publisher": chunk.metadata.get("publisher"),
            "source_url": chunk.metadata.get("source_url"),
            "document_version": chunk.metadata.get("document_version"),
            "reviewed_at": chunk.metadata.get("reviewed_at"),
            "parent_category": chunk.metadata.get("parent_category"),
            "child_categories": chunk.metadata.get("child_categories", []),
            "applicable_population": chunk.metadata.get("applicable_population", []),
            "evidence_level": chunk.metadata.get("evidence_level"),
            "medical_boundary": chunk.metadata.get("medical_boundary"),
            "source_type": chunk.metadata.get("source_type"),
        }

    def _location(self) -> str:
        return f"{self.config.host}:{self.config.port}/{self.config.dbname}"
