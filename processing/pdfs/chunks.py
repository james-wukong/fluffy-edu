import re
from typing import Any, TypedDict

import structlog
from extractor import PageResult


class ChunkResult(TypedDict):
    text: str
    metadata: dict[str, Any]


class SmartChunker:
    def __init__(
        self, chunk_size: int = 512, overlap: int = 64, respect_paragraphs: bool = True
    ):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if overlap < 0:
            raise ValueError("overlap must be >= 0")
        if overlap >= chunk_size:
            overlap = chunk_size - 1

        self.chunk_size = chunk_size
        self.overlap = overlap
        self.respect_paragraphs = respect_paragraphs

    def chunk(self, page_result: PageResult) -> list[ChunkResult]:
        text = page_result["text"].strip()
        if not text:
            return []

        if self.respect_paragraphs:
            return self._paragraph_aware_chunk(text, page_result["metadata"])
        return self._fixed_size_chunk(text, page_result["metadata"])

    def _fixed_size_chunk(
        self, text: str, metadata: dict[str, Any]
    ) -> list[ChunkResult]:
        """Split by word count with overlap — ignores paragraph boundaries"""

        words = text.split()
        chunks = []
        step = self.chunk_size - self.overlap
        start: int = 0

        while start < len(words):
            end = start + self.chunk_size
            chunk_words = words[start:end]

            chunks.append(self._make_chunk(chunk_words, metadata, len(chunks)))

            # Move forward by chunk_size minus overlap
            # so the next chunk starts overlap words before the end
            start += step

        return chunks

    def _paragraph_aware_chunk(
        self, text: str, metadata: dict[str, Any]
    ) -> list[ChunkResult]:
        """Respect paragraph boundaries — chunks make more sense"""

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        chunks = []

        current_words: list[str] = []
        logger = structlog.get_logger()
        for para in paragraphs:
            para_words = para.split()
            logger.info("para", para)
            # If paragraph itself is too large, split it
            if len(para_words) > self.chunk_size:
                logger.info("para_words > self.chunk_size", len(para), self.chunk_size)
                if current_words:
                    logger.info("current_words", current_words)
                    chunks.append(
                        self._make_chunk(current_words, metadata, len(chunks))
                    )
                    current_words = current_words[-self.overlap :]

                large_chunks = self._fixed_size_chunk(para, metadata)
                logger.info("large_chunks", large_chunks)
                for item in large_chunks:
                    item["metadata"]["chunk_index"] = len(chunks)
                    chunks.append(item)
                    logger.info("large_chunks item:", item)

                current_words = []
                continue

            if len(current_words) + len(para_words) > self.chunk_size:
                chunks.append(self._make_chunk(current_words, metadata, len(chunks)))
                current_words = current_words[-self.overlap :]

            logger.info("current_words extending para_words:")
            current_words.extend(para_words)

        if current_words:
            chunks.append(self._make_chunk(current_words, metadata, len(chunks)))

        return chunks

    def _make_chunk(
        self,
        words: list[str],
        metadata: dict[str, Any],
        index: int,
    ) -> dict[str, Any]:
        return {
            "text": " ".join(words),
            "metadata": {
                "chunk_index": index,
                "word_count": len(words),
            }
            | metadata,
        }

    def _detect_section_header(self, line: str) -> bool:
        """Detect if a line is a section header"""
        line = line.strip()

        return (
            (line.isupper() and len(line) > 5)
            or bool(re.match(r"^\d+(\.\d+)*\s+[A-Z]", line))
            or bool(re.match(r"^(CHAPTER|SECTION|PART)\s+", line, re.I))
        )

    def validate_chunk(self, chunk: ChunkResult) -> tuple[bool, str]:
        text = chunk["text"]

        # Too short
        if len(text.split()) < 20:
            return False, "too_short"

        # Too long (chunker bug)
        if len(text.split()) > 800:
            return False, "too_long"

        # Mostly numbers/symbols (probably a table extraction artifact)
        alpha_ratio = sum(c.isalpha() for c in text) / max(len(text), 1)
        if alpha_ratio < 0.4:
            return False, "low_alpha_ratio"

        # Repeated characters (OCR garbage)
        if re.search(r"(.)\1{6,}", text):
            return False, "repeated_chars"

        # Mostly gibberish (OCR failure)
        words = text.split()
        long_words = [w for w in words if len(w) > 20]
        if len(long_words) / max(len(words), 1) > 0.2:
            return False, "too_many_long_words"

        return True, "ok"


chunker = SmartChunker(chunk_size=512, overlap=64, respect_paragraphs=True)

text: PageResult = {
    "text": """
Hello world this

This is paragraph two with more words. Input Types: Requires an iterable; passing a non-iterable (like an integer or boolean) will raise a TypeError.

This is paragraph three.
""",
    "metadata": {"page": 1},
}

print(chunker.chunk(text))
