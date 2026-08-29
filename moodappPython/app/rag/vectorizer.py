from __future__ import annotations

from .contracts import ChunkEmbedding, KnowledgeChunk, VectorizationError, VectorizationSummary
from .embedding_gateway import EmbeddingGateway
from ..config import EMBEDDING_BATCH_SIZE


class KnowledgeVectorizerError(Exception):
    pass


class KnowledgeVectorizer:
    def __init__(
        self,
        embedding_gateway: EmbeddingGateway | None = None,
        *,
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ) -> None:
        if batch_size < 1 or batch_size > 128:
            raise KnowledgeVectorizerError("batch_size must be between 1 and 128")
        self.embedding_gateway = embedding_gateway or EmbeddingGateway()
        self.batch_size = batch_size

    async def vectorize_chunks(self, chunks: list[KnowledgeChunk]) -> VectorizationSummary:
        vectors: list[ChunkEmbedding] = []
        errors: list[VectorizationError] = []
        dimensions: int | None = None
        searchable_children = [chunk for chunk in chunks if chunk.chunk_level == "child"]
        parent_chunks = [chunk for chunk in chunks if chunk.chunk_level == "parent"]

        # Only children participate in similarity search. Parent rows receive a
        # zero vector after dimensions are known and are loaded by exact id.
        for batch in self._batches(searchable_children, self.batch_size):
            try:
                embeddings = await self.embedding_gateway.embed_texts([chunk.content for chunk in batch])
                if len(embeddings) != len(batch):
                    raise KnowledgeVectorizerError("Embedding batch size mismatch")
                for chunk, embedding in zip(batch, embeddings, strict=True):
                    if dimensions is None:
                        dimensions = len(embedding)
                    elif len(embedding) != dimensions:
                        raise KnowledgeVectorizerError("Embedding dimensions changed across batches")
                    vectors.append(self._to_chunk_embedding(chunk, embedding))
            except Exception as exc:  # noqa: BLE001 - converted to structured vectorization error.
                for chunk in batch:
                    errors.append(
                        VectorizationError(
                            chunk_id=chunk.chunk_id,
                            error_code=exc.__class__.__name__,
                            message=str(exc),
                        )
                    )

        if dimensions is not None:
            for chunk in parent_chunks:
                vectors.append(self._to_chunk_embedding(chunk, [0.0] * dimensions))
        elif parent_chunks:
            for chunk in parent_chunks:
                errors.append(VectorizationError(
                    chunk_id=chunk.chunk_id,
                    error_code="MissingChildEmbeddingDimensions",
                    message="Cannot store parent context before child embedding dimensions are known",
                ))

        return VectorizationSummary(
            chunk_count=len(chunks),
            vector_count=len(vectors),
            failed_count=len(errors),
            embedding_model=self.embedding_gateway.model or "unconfigured",
            dimensions=dimensions,
            vectors=vectors,
            errors=errors,
        )

    def _to_chunk_embedding(self, chunk: KnowledgeChunk, embedding: list[float]) -> ChunkEmbedding:
        return ChunkEmbedding(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            source=chunk.source,
            category=chunk.category,
            content_hash=chunk.content_hash,
            document_hash=chunk.document_hash,
            embedding=embedding,
            dimensions=len(embedding),
            embedding_model=self.embedding_gateway.model,
            metadata={
                "file_path": chunk.metadata.get("file_path"),
                "file_name": chunk.metadata.get("file_name"),
                "file_type": chunk.metadata.get("file_type"),
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "heading_path": chunk.heading_path,
                "ordinal": chunk.ordinal,
                "chunk_level": chunk.chunk_level,
                "parent_chunk_id": chunk.parent_chunk_id,
            },
        )

    @staticmethod
    def _batches(chunks: list[KnowledgeChunk], batch_size: int) -> list[list[KnowledgeChunk]]:
        return [chunks[start : start + batch_size] for start in range(0, len(chunks), batch_size)]
