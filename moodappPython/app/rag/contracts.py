from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field



KnowledgeCategory = Literal[
    "student_psychology",
    "stress_management",
    "sleep_management",
    "crisis_guidelines",
    "school_resources",
]

KNOWLEDGE_CATEGORIES: tuple[str, ...] = (
    "student_psychology",
    "stress_management",
    "sleep_management",
    "crisis_guidelines",
    "school_resources",
)

SUPPORTED_DOCUMENT_EXTENSIONS: tuple[str, ...] = (
    ".md",
    ".markdown",
    ".txt",
    ".pdf",
    ".docx",
)

#===================知识库定义 =====================

class ParsedDocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    file_type: str = Field(min_length=1)
    file_size_bytes: int = Field(ge=0)
    content_hash: str = Field(min_length=64, max_length=64)
    modified_at: datetime | None = None
    parser: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    title: str | None = None
    publisher: str | None = None
    source_url: str | None = None
    document_version: str | None = None
    reviewed_at: datetime | None = None
    parent_category: str | None = None
    child_categories: list[str] = Field(default_factory=list)
    applicable_population: list[str] = Field(default_factory=list)
    evidence_level: Literal["project_curated", "public_guidance", "school_resource", "crisis_guideline"] | None = None
    medical_boundary: str | None = None
    source_type: Literal["project_curated", "public_reference", "school_resource"] | None = None


#单个已解析的知识文档
class ParsedKnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=300)
    category: KnowledgeCategory
    content: str = Field(min_length=1)
    metadata: ParsedDocumentMetadata


#解析错误信息
class DocumentParseError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(min_length=1)
    category: str = Field(min_length=1)
    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1)


#解析操作的汇总统计
class KnowledgeParseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_path: str = Field(min_length=1)
    total_files: int = Field(ge=0)
    parsed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    documents: list[ParsedKnowledgeDocument] = Field(default_factory=list)
    errors: list[DocumentParseError] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)


class ChunkingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # max/min/overlap describe the searchable child chunks. Parent chunks retain
    # the complete section context and are returned only after a child hit.
    max_chars: int = Field(default=220, ge=120, le=1000)
    min_chars: int = Field(default=80, ge=20, le=500)
    overlap_chars: int = Field(default=30, ge=0, le=200)
    parent_max_chars: int = Field(default=1200, ge=500, le=4000)
    parent_min_chars: int = Field(default=400, ge=50, le=2000)


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    category: KnowledgeCategory
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    chunk_level: Literal["parent", "child"] = "child"
    parent_chunk_id: str | None = None
    ordinal: int = Field(ge=0)
    content: str = Field(min_length=1)
    heading_path: list[str] = Field(default_factory=list)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    token_count_estimate: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)
    document_hash: str = Field(min_length=64, max_length=64)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkingError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ChunkingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    config: ChunkingConfig
    chunks: list[KnowledgeChunk] = Field(default_factory=list)
    errors: list[ChunkingError] = Field(default_factory=list)


class ChunkEmbedding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    category: KnowledgeCategory
    content_hash: str = Field(min_length=64, max_length=64)
    document_hash: str = Field(min_length=64, max_length=64)
    embedding: list[float] = Field(min_length=1)
    dimensions: int = Field(ge=1)
    embedding_model: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorizationError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class VectorizationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_count: int = Field(ge=0)
    vector_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    embedding_model: str = Field(min_length=1)
    dimensions: int | None = Field(default=None, ge=1)
    vectors: list[ChunkEmbedding] = Field(default_factory=list)
    errors: list[VectorizationError] = Field(default_factory=list)


class VectorStoreError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str | None = None
    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class VectorStoreSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_name: str = Field(min_length=1)
    persist_directory: str = Field(min_length=1)
    chunk_count: int = Field(ge=0)
    upserted_count: int = Field(ge=0)
    inserted_count: int = Field(default=0, ge=0)
    updated_count: int = Field(default=0, ge=0)
    deleted_count: int = Field(default=0, ge=0)
    unchanged_count: int = Field(default=0, ge=0)
    failed_count: int = Field(ge=0)
    embedding_model: str = Field(min_length=1)
    dimensions: int | None = Field(default=None, ge=1)
    errors: list[VectorStoreError] = Field(default_factory=list)


class KnowledgeIndexMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model: str = Field(min_length=1)
    dimensions: int = Field(ge=1)
    chunker_version: str = Field(min_length=1)
    chunking_config: ChunkingConfig
    knowledge_version: str = Field(min_length=1)
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)


class RetrievalCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    category: KnowledgeCategory
    chunk_id: str = Field(min_length=1)
    chunk_level: Literal["parent", "child"] = "child"
    parent_chunk_id: str | None = None
    content: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    file_path: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    file_type: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    document_hash: str = Field(min_length=64, max_length=64)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    heading_path: list[str] = Field(default_factory=list)
    title: str | None = None
    publisher: str | None = None
    source_url: str | None = None
    document_version: str | None = None
    reviewed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class RetrievalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    top_k: int = Field(ge=1, le=50)
    min_score: float = Field(ge=0.0, le=1.0)
    result_count: int = Field(ge=0)
    has_evidence: bool
    no_evidence_reason: str | None = None
    citations: list[RetrievalCitation] = Field(default_factory=list)
    errors: list[RetrievalError] = Field(default_factory=list)
    warnings: list[RetrievalError] = Field(default_factory=list)
    retrieval_strategy: str = "vector_only"
    category_fallback_used: bool = False
    category_candidate_counts: dict[str, int] = Field(default_factory=dict)
    candidate_count: int = Field(default=0, ge=0)


class RerankItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    relevance_score: float = Field(ge=0.0, le=1.0)


class RerankTraceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    vector_score: float = Field(ge=0.0, le=1.0)
    keyword_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rerank_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)


class RerankSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_count: int = Field(ge=0)
    output_count: int = Field(ge=0)
    citations: list[RetrievalCitation] = Field(default_factory=list)
    trace: list[RerankTraceItem] = Field(default_factory=list)
    errors: list[RetrievalError] = Field(default_factory=list)
