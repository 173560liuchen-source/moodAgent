from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .contracts import (
    ChunkingConfig,
    ChunkingError,
    ChunkingSummary,
    KnowledgeChunk,
    ParsedKnowledgeDocument,
)


CHUNKER_VERSION = "3.0.0-parent-child"


class KnowledgeChunkerError(Exception):
    pass


@dataclass(frozen=True)
class TextBlock:
    text: str
    char_start: int
    char_end: int
    heading_path: list[str]


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    char_start: int
    char_end: int
    heading_path: list[str]
    overlap_from_previous_chars: int = 0


class KnowledgeChunker:
    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()
        if self.config.overlap_chars >= self.config.max_chars:
            raise KnowledgeChunkerError("overlap_chars must be smaller than max_chars")
        if self.config.min_chars > self.config.max_chars:
            raise KnowledgeChunkerError("min_chars must be smaller than or equal to max_chars")
        if self.config.parent_min_chars > self.config.parent_max_chars:
            raise KnowledgeChunkerError("parent_min_chars must be smaller than or equal to parent_max_chars")
        if self.config.max_chars >= self.config.parent_max_chars:
            raise KnowledgeChunkerError("child max_chars must be smaller than parent_max_chars")

    def chunk_document(self, document: ParsedKnowledgeDocument) -> list[KnowledgeChunk]:
        blocks = self._split_into_blocks(document.content)
        parent_drafts = self._build_chunk_drafts(
            blocks,
            max_chars=self.config.parent_max_chars,
            min_chars=self.config.parent_min_chars,
            overlap_chars=0,
        )
        chunks: list[KnowledgeChunk] = []

        for parent_ordinal, parent_draft in enumerate(parent_drafts):
            parent_hash = hashlib.sha256(parent_draft.content.encode("utf-8")).hexdigest()
            parent_id = self._parent_chunk_id(document.document_id, parent_ordinal, parent_hash)
            chunks.append(
                self._knowledge_chunk(
                    document=document,
                    draft=parent_draft,
                    chunk_id=parent_id,
                    ordinal=parent_ordinal,
                    content_hash=parent_hash,
                    chunk_level="parent",
                    parent_chunk_id=None,
                    parent_ordinal=parent_ordinal,
                )
            )

            child_blocks = self._child_blocks(parent_draft)
            child_drafts = self._build_chunk_drafts(
                child_blocks,
                max_chars=self.config.max_chars,
                min_chars=self.config.min_chars,
                overlap_chars=self.config.overlap_chars,
            )
            for child_ordinal, child_draft in enumerate(child_drafts):
                child_hash = hashlib.sha256(child_draft.content.encode("utf-8")).hexdigest()
                child_id = self._child_chunk_id(parent_id, child_ordinal, child_hash)
                chunks.append(
                    self._knowledge_chunk(
                        document=document,
                        draft=child_draft,
                        chunk_id=child_id,
                        ordinal=child_ordinal,
                        content_hash=child_hash,
                        chunk_level="child",
                        parent_chunk_id=parent_id,
                        parent_ordinal=parent_ordinal,
                    )
                )

        return chunks

    def _knowledge_chunk(
        self,
        *,
        document: ParsedKnowledgeDocument,
        draft: ChunkDraft,
        chunk_id: str,
        ordinal: int,
        content_hash: str,
        chunk_level: str,
        parent_chunk_id: str | None,
        parent_ordinal: int,
    ) -> KnowledgeChunk:
        return KnowledgeChunk(
            source=document.source,
            category=document.category,
            chunk_id=chunk_id,
            document_id=document.document_id,
            chunk_level=chunk_level,  # type: ignore[arg-type]
            parent_chunk_id=parent_chunk_id,
            ordinal=ordinal,
            content=draft.content,
            heading_path=draft.heading_path,
            char_start=draft.char_start,
            char_end=draft.char_end,
            token_count_estimate=self._estimate_tokens(draft.content),
            content_hash=content_hash,
            document_hash=document.metadata.content_hash,
            metadata={
                "file_path": document.metadata.file_path,
                "file_name": document.metadata.file_name,
                "file_type": document.metadata.file_type,
                "title": document.metadata.title,
                "publisher": document.metadata.publisher,
                "source_url": document.metadata.source_url,
                "document_version": document.metadata.document_version,
                "reviewed_at": document.metadata.reviewed_at.isoformat() if document.metadata.reviewed_at else None,
                "parent_category": document.metadata.parent_category,
                "child_categories": document.metadata.child_categories,
                "applicable_population": document.metadata.applicable_population,
                "evidence_level": document.metadata.evidence_level,
                "medical_boundary": document.metadata.medical_boundary,
                "source_type": document.metadata.source_type,
                "source": document.source,
                "category": document.category,
                "heading_path": draft.heading_path,
                "heading_title": draft.heading_path[-1] if draft.heading_path else document.metadata.title,
                "applicable_audience": self._extract_labeled_value(
                    document.content, ("适用对象", "适用人群")
                ),
                "document_content_hash": document.metadata.content_hash,
                "chunker": "KnowledgeChunker",
                "chunker_version": CHUNKER_VERSION,
                "chunk_level": chunk_level,
                "parent_chunk_id": parent_chunk_id,
                "parent_ordinal": parent_ordinal,
                "overlap_from_previous_chars": draft.overlap_from_previous_chars,
            },
        )

    def _child_blocks(self, parent: ChunkDraft) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        cursor = 0
        for sentence in self._sentence_units(parent.content):
            sentence_start = parent.content.find(sentence, cursor)
            if sentence_start < 0:
                sentence_start = cursor
            sentence_end = sentence_start + len(sentence)
            cursor = sentence_end
            if len(sentence) <= self.config.max_chars:
                blocks.append(TextBlock(
                    text=sentence,
                    char_start=parent.char_start + sentence_start,
                    char_end=parent.char_start + sentence_end,
                    heading_path=list(parent.heading_path),
                ))
            else:
                blocks.extend(self._hard_split_text(
                    sentence,
                    parent.char_start + sentence_start,
                    parent.heading_path,
                    max_chars=self.config.max_chars,
                ))
        return blocks

    def chunk_documents(self, documents: list[ParsedKnowledgeDocument]) -> ChunkingSummary:
        chunks: list[KnowledgeChunk] = []
        errors: list[ChunkingError] = []

        for document in documents:
            try:
                chunks.extend(self.chunk_document(document))
            except Exception as exc:  # noqa: BLE001 - converted to structured chunking error.
                errors.append(
                    ChunkingError(
                        document_id=document.document_id,
                        source=document.source,
                        error_code=exc.__class__.__name__,
                        message=str(exc),
                    )
                )

        return ChunkingSummary(
            document_count=len(documents),
            chunk_count=len(chunks),
            failed_count=len(errors),
            config=self.config,
            chunks=chunks,
            errors=errors,
        )

    def _split_into_blocks(self, content: str) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        headings: list[str] = []
        pending_lines: list[str] = []
        pending_start: int | None = None
        pending_heading_path: list[str] = []
        offset = 0

        for line in content.splitlines(keepends=True):
            raw_line = line
            stripped = raw_line.strip()
            line_start = offset
            line_end = offset + len(raw_line)
            heading = self._heading_info(stripped)

            if heading is not None:
                self._flush_pending_block(
                    blocks,
                    pending_lines,
                    pending_start,
                    line_start,
                    pending_heading_path,
                )
                pending_lines = []
                pending_start = None
                level, title = heading
                headings = headings[: level - 1] + [title]
                offset = line_end
                continue

            if self._is_page_artifact(stripped):
                self._flush_pending_block(
                    blocks,
                    pending_lines,
                    pending_start,
                    line_start,
                    pending_heading_path,
                )
                pending_lines = []
                pending_start = None
                offset = line_end
                continue

            if not stripped:
                self._flush_pending_block(
                    blocks,
                    pending_lines,
                    pending_start,
                    line_start,
                    pending_heading_path,
                )
                pending_lines = []
                pending_start = None
                offset = line_end
                continue

            if self._starts_new_semantic_unit(stripped) and pending_lines:
                self._flush_pending_block(
                    blocks,
                    pending_lines,
                    pending_start,
                    line_start,
                    pending_heading_path,
                )
                pending_lines = []
                pending_start = None

            if pending_start is None:
                pending_start = line_start
                pending_heading_path = list(headings)
            pending_lines.append(raw_line)
            offset = line_end

        self._flush_pending_block(
            blocks,
            pending_lines,
            pending_start,
            len(content),
            pending_heading_path,
        )
        return blocks

    @staticmethod
    def _heading_info(text: str) -> tuple[int, str] | None:
        markdown = re.match(r"^(#{1,6})\s+(.+?)\s*$", text)
        if markdown:
            return len(markdown.group(1)), markdown.group(2).strip()

        numbered = re.match(r"^(\d+(?:\.\d+)*)[.、]\s*(.+?)\s*$", text)
        if numbered:
            title = numbered.group(2).strip()
            # Numbered instructions normally end in sentence punctuation; short
            # label-like lines are treated as section headings.
            if len(title) <= 24 and not re.search(r"[。！？!?；;：:]$", title):
                return numbered.group(1).count(".") + 1, title
        if text == "权威来源与更新说明":
            return 1, text
        return None

    @staticmethod
    def _is_page_artifact(text: str) -> bool:
        return bool(
            re.match(r"^第\s*\d+\s*页$", text)
            or re.match(r"^.+?\s*[|｜]\s*第?\s*\d+\s*页?$", text)
            or re.match(r"^心晴\s*AI\s*[·・].+$", text, flags=re.IGNORECASE)
        )

    @staticmethod
    def _starts_new_semantic_unit(text: str) -> bool:
        return bool(
            re.match(r"^[•●▪◦]\s*", text)
            or re.match(r"^\d+[.、]\s+", text)
            or re.match(
                r"^(核心原则|先说明|重要说明|紧急提示|今晚可以做的三件事|"
                r"就医渠道|一般情况|重要例外|系统回答要求|应该说|应该做|"
                r"禁止|系统边界|检索关键词|权威来源与更新说明)\s*$",
                text,
            )
        )

    @staticmethod
    def _extract_labeled_value(content: str, labels: tuple[str, ...]) -> str | None:
        for label in labels:
            match = re.search(rf"^{re.escape(label)}\s*[：:]\s*(.+)$", content, flags=re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None

    def _flush_pending_block(
        self,
        blocks: list[TextBlock],
        pending_lines: list[str],
        pending_start: int | None,
        char_end: int,
        heading_path: list[str],
    ) -> None:
        if pending_start is None or not pending_lines:
            return

        raw_text = "".join(pending_lines)
        stripped_text = raw_text.strip()
        if not stripped_text:
            return

        leading_spaces = len(raw_text) - len(raw_text.lstrip())
        trailing_spaces = len(raw_text) - len(raw_text.rstrip())
        blocks.extend(
            self._split_oversized_block(
                stripped_text,
                pending_start + leading_spaces,
                char_end - trailing_spaces,
                heading_path,
            )
        )

    def _split_oversized_block(
        self,
        text: str,
        char_start: int,
        char_end: int,
        heading_path: list[str],
    ) -> list[TextBlock]:
        if len(text) <= self.config.parent_max_chars:
            return [TextBlock(text=text, char_start=char_start, char_end=char_end, heading_path=list(heading_path))]

        blocks: list[TextBlock] = []
        cursor = 0
        for sentence in self._sentence_units(text):
            sentence_start = text.find(sentence, cursor)
            if sentence_start < 0:
                sentence_start = cursor
            sentence_end = sentence_start + len(sentence)
            cursor = sentence_end

            if len(sentence) <= self.config.parent_max_chars:
                blocks.append(
                    TextBlock(
                        text=sentence.strip(),
                        char_start=char_start + sentence_start,
                        char_end=char_start + sentence_end,
                        heading_path=list(heading_path),
                    )
                )
                continue

            blocks.extend(self._hard_split_text(
                sentence,
                char_start + sentence_start,
                heading_path,
                max_chars=self.config.parent_max_chars,
            ))

        return blocks

    def _build_chunk_drafts(
        self,
        blocks: list[TextBlock],
        *,
        max_chars: int,
        min_chars: int,
        overlap_chars: int,
    ) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        current_texts: list[str] = []
        current_start: int | None = None
        current_end: int | None = None
        current_heading: list[str] = []

        for block in blocks:
            if current_texts and block.heading_path != current_heading:
                drafts.append(
                        self._with_overlap(
                            drafts,
                            self._draft(current_texts, current_start, current_end, current_heading),
                            overlap_chars,
                        )
                )
                current_texts = []
                current_start = None
                current_end = None
                current_heading = []

            candidate_text = self._join_blocks(current_texts + [block.text])
            if current_texts and len(candidate_text) > max_chars:
                drafts.append(
                    self._with_overlap(
                        drafts,
                        self._draft(current_texts, current_start, current_end, current_heading),
                        overlap_chars,
                    )
                )
                current_texts = [block.text]
                current_start = block.char_start
                current_end = block.char_end
                current_heading = list(block.heading_path)
                continue

            if current_start is None:
                current_start = block.char_start
                current_heading = list(block.heading_path)
            current_texts.append(block.text)
            current_end = block.char_end
            current_heading = list(block.heading_path)

        if current_texts:
            draft = self._draft(current_texts, current_start, current_end, current_heading)
            if (
                drafts
                and len(draft.content) < min_chars
                and drafts[-1].heading_path == draft.heading_path
                and len(self._join_blocks([drafts[-1].content, draft.content])) <= max_chars
            ):
                previous = drafts.pop()
                merged = ChunkDraft(
                    content=self._join_blocks([previous.content, draft.content]),
                    char_start=previous.char_start,
                    char_end=draft.char_end,
                    heading_path=draft.heading_path or previous.heading_path,
                    overlap_from_previous_chars=previous.overlap_from_previous_chars,
                )
                drafts.append(merged)
            else:
                drafts.append(self._with_overlap(drafts, draft, overlap_chars))

        return drafts

    def _with_overlap(
        self,
        drafts: list[ChunkDraft],
        draft: ChunkDraft,
        overlap_chars: int,
    ) -> ChunkDraft:
        if not drafts or overlap_chars == 0:
            return draft

        previous = drafts[-1].content
        overlap = previous[-overlap_chars:].strip()
        if not overlap:
            return draft

        content = self._join_blocks([overlap, draft.content])
        return ChunkDraft(
            content=content,
            char_start=draft.char_start,
            char_end=draft.char_end,
            heading_path=draft.heading_path,
            overlap_from_previous_chars=len(overlap),
        )

    @staticmethod
    def _draft(
        texts: list[str],
        char_start: int | None,
        char_end: int | None,
        heading_path: list[str],
    ) -> ChunkDraft:
        if char_start is None or char_end is None:
            raise KnowledgeChunkerError("Cannot create an empty chunk")
        return ChunkDraft(
            content=KnowledgeChunker._join_blocks(texts),
            char_start=char_start,
            char_end=char_end,
            heading_path=list(heading_path),
        )

    @staticmethod
    def _sentence_units(text: str) -> list[str]:
        units = re.split(r"(?<=[。！？!?；;])\s*", text)
        return [unit.strip() for unit in units if unit.strip()]

    def _hard_split_text(
        self,
        text: str,
        char_start: int,
        heading_path: list[str],
        *,
        max_chars: int,
    ) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        step = max_chars
        for start in range(0, len(text), step):
            end = min(start + step, len(text))
            piece = text[start:end].strip()
            if not piece:
                continue
            leading = len(text[start:end]) - len(text[start:end].lstrip())
            trailing = len(text[start:end]) - len(text[start:end].rstrip())
            blocks.append(
                TextBlock(
                    text=piece,
                    char_start=char_start + start + leading,
                    char_end=char_start + end - trailing,
                    heading_path=list(heading_path),
                )
            )
        return blocks

    @staticmethod
    def _join_blocks(texts: list[str]) -> str:
        return "\n\n".join(text.strip() for text in texts if text.strip()).strip()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)))

    @staticmethod
    def _parent_chunk_id(document_id: str, ordinal: int, content_hash: str) -> str:
        return f"{document_id}-parent-{ordinal:04d}-{content_hash[:8]}"

    @staticmethod
    def _child_chunk_id(parent_chunk_id: str, ordinal: int, content_hash: str) -> str:
        return f"{parent_chunk_id}-child-{ordinal:04d}-{content_hash[:8]}"
