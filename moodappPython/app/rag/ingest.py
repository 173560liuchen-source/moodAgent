from __future__ import annotations

import hashlib
import json

from .chunker import KnowledgeChunker
from .contracts import ChunkingConfig
from .document_parser import KnowledgeDocumentParser
from .embedding_gateway import EmbeddingGateway
from .vectorizer import KnowledgeVectorizer
from .vector_store import PgVectorKnowledgeStore
from .chunker import CHUNKER_VERSION


class IngestionNotImplementedError(NotImplementedError):
    pass


def parse_knowledge_documents(knowledge_root: str):
    parser = KnowledgeDocumentParser(knowledge_root)
    return parser.parse_all()


def chunk_knowledge_documents(knowledge_root: str, config: ChunkingConfig | None = None):
    parse_summary = parse_knowledge_documents(knowledge_root)
    chunker = KnowledgeChunker(config)
    chunk_summary = chunker.chunk_documents(parse_summary.documents)
    return {
        "parse_summary": parse_summary,
        "chunk_summary": chunk_summary,
    }


async def vectorize_knowledge_documents(
    knowledge_root: str,
    chunking_config: ChunkingConfig | None = None,
    embedding_gateway: EmbeddingGateway | None = None,
):
    chunk_result = chunk_knowledge_documents(knowledge_root, chunking_config)
    vectorizer = KnowledgeVectorizer(embedding_gateway)
    vector_summary = await vectorizer.vectorize_chunks(chunk_result["chunk_summary"].chunks)
    return {
        "parse_summary": chunk_result["parse_summary"],
        "chunk_summary": chunk_result["chunk_summary"],
        "vector_summary": vector_summary,
    }


async def build_vector_store(
    knowledge_root: str,
    chunking_config: ChunkingConfig | None = None,
    embedding_gateway: EmbeddingGateway | None = None,
    vector_store: PgVectorKnowledgeStore | None = None,
    *,
    prune_missing: bool = False,
):
    vector_result = await vectorize_knowledge_documents(
        knowledge_root,
        chunking_config,
        embedding_gateway,
    )
    store = vector_store or PgVectorKnowledgeStore()
    chunk_summary = vector_result["chunk_summary"]
    version_payload = {
        "documents": sorted(chunk.document_hash for chunk in chunk_summary.chunks),
        "chunker_version": CHUNKER_VERSION,
        "config": chunk_summary.config.model_dump(mode="json"),
        "embedding_model": vector_result["vector_summary"].embedding_model,
    }
    knowledge_version = hashlib.sha256(
        json.dumps(version_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    storage_summary = store.sync_chunks(
        chunks=vector_result["chunk_summary"].chunks,
        vector_summary=vector_result["vector_summary"],
        prune_missing=prune_missing,
        knowledge_version=knowledge_version,
        chunking_config=chunk_summary.config.model_dump(mode="json"),
        chunker_version=CHUNKER_VERSION,
    )
    return {
        "parse_summary": vector_result["parse_summary"],
        "chunk_summary": vector_result["chunk_summary"],
        "vector_summary": vector_result["vector_summary"],
        "storage_summary": storage_summary,
        "knowledge_version": knowledge_version,
    }


async def ingest_document(*args, **kwargs):
    return await build_vector_store(*args, **kwargs)
