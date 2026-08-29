from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.rag.contracts import ChunkingConfig
from app.rag.ingest import build_vector_store


def _document_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    parse_summary = result["parse_summary"]
    chunks = result["chunk_summary"].chunks
    counts: dict[str, int] = {}
    parent_counts: dict[str, int] = {}
    child_counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.document_id] = counts.get(chunk.document_id, 0) + 1
        target = parent_counts if chunk.chunk_level == "parent" else child_counts
        target[chunk.document_id] = target.get(chunk.document_id, 0) + 1
    return [
        {
            "document_id": document.document_id,
            "file_name": document.metadata.file_name,
            "category": document.category,
            "extracted_characters": len(document.content),
            "chunk_count": counts.get(document.document_id, 0),
            "parent_chunk_count": parent_counts.get(document.document_id, 0),
            "child_chunk_count": child_counts.get(document.document_id, 0),
            "content_hash": document.metadata.content_hash,
        }
        for document in parse_summary.documents
    ]


async def run(args: argparse.Namespace) -> dict[str, Any]:
    result = await build_vector_store(
        str(Path(args.source).resolve()),
        ChunkingConfig(
            max_chars=args.max_chars,
            min_chars=args.min_chars,
            overlap_chars=args.overlap_chars,
            parent_max_chars=args.parent_max_chars,
            parent_min_chars=args.parent_min_chars,
        ),
        prune_missing=args.rebuild,
    )
    parse_summary = result["parse_summary"]
    chunk_summary = result["chunk_summary"]
    vector_summary = result["vector_summary"]
    storage_summary = result["storage_summary"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "knowledge_version": result["knowledge_version"],
        "source": parse_summary.root_path,
        "rebuild": args.rebuild,
        "files": {
            "scanned": parse_summary.total_files,
            "parsed": parse_summary.parsed_count,
            "failed": parse_summary.failed_count,
            "skipped": parse_summary.skipped_count,
        },
        "documents": _document_rows(result),
        "chunking": {
            **chunk_summary.config.model_dump(mode="json"),
            "chunk_count": chunk_summary.chunk_count,
            "failed_count": chunk_summary.failed_count,
        },
        "embedding": {
            "model": vector_summary.embedding_model,
            "dimensions": vector_summary.dimensions,
            "vector_count": vector_summary.vector_count,
            "failed_count": vector_summary.failed_count,
        },
        "storage": storage_summary.model_dump(mode="json"),
        "errors": [
            *[error.model_dump(mode="json") for error in parse_summary.errors],
            *[error.model_dump(mode="json") for error in chunk_summary.errors],
            *[error.model_dump(mode="json") for error in vector_summary.errors],
            *[error.model_dump(mode="json") for error in storage_summary.errors],
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and verify the MoodApp RAG index")
    parser.add_argument("--source", default="knowledge")
    parser.add_argument("--report", default="reports/knowledge-ingestion.json")
    parser.add_argument("--rebuild", action="store_true", help="Prune chunks missing from this snapshot")
    parser.add_argument("--max-chars", type=int, default=220, help="Searchable child chunk size")
    parser.add_argument("--min-chars", type=int, default=80, help="Minimum child chunk size")
    parser.add_argument("--overlap-chars", type=int, default=30, help="Child chunk overlap")
    parser.add_argument("--parent-max-chars", type=int, default=1200)
    parser.add_argument("--parent-min-chars", type=int, default=400)
    args = parser.parse_args()
    report = asyncio.run(run(args))
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "knowledge_version": report["knowledge_version"],
        "files": report["files"],
        "chunk_count": report["chunking"]["chunk_count"],
        "storage": report["storage"],
        "report": str(report_path.resolve()),
    }, ensure_ascii=False, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
