import re
from typing import Any


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

    def chunk(self, text: str, page_num: int) -> list[dict[str, Any]]:
        text = text.strip()
        if not text:
            return []

        if self.respect_paragraphs:
            return self._paragraph_aware_chunk(text, page_num)
        return self._fixed_size_chunk(text, page_num)

    def _fixed_size_chunk(self, text: str, page_num: int) -> list[dict[str, Any]]:
        """Split by word count with overlap — ignores paragraph boundaries"""

        words = text.split()
        chunks = []
        step = self.chunk_size - self.overlap
        start: int = 0

        while start < len(words):
            end = start + self.chunk_size
            chunk_words = words[start:end]

            chunks.append(self._make_chunk(chunk_words, page_num, len(chunks)))

            # Move forward by chunk_size minus overlap
            # so the next chunk starts overlap words before the end
            start += step

        return chunks

    def _paragraph_aware_chunk(self, text: str, page_num: int) -> list[dict[str, Any]]:
        """Respect paragraph boundaries — chunks make more sense"""

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        chunks = []

        current_words: list[str] = []

        for para in paragraphs:
            para_words = para.split()

            # If paragraph itself is too large, split it
            if len(para_words) > self.chunk_size:
                if current_words:
                    chunks.append(
                        self._make_chunk(current_words, page_num, len(chunks))
                    )
                    current_words = current_words[-self.overlap :]

                large_chunks = self._fixed_size_chunk(para, page_num)
                for item in large_chunks:
                    item["chunk_index"] = len(chunks)
                    chunks.append(item)

                current_words = []
                continue

            if len(current_words) + len(para_words) > self.chunk_size:
                chunks.append(self._make_chunk(current_words, page_num, len(chunks)))
                current_words = current_words[-self.overlap :]

            current_words.extend(para_words)

        if current_words:
            chunks.append(self._make_chunk(current_words, page_num, len(chunks)))

        return chunks

    def _make_chunk(
        self,
        words: list[str],
        page_num: int,
        index: int,
    ) -> dict[str, Any]:
        return {
            "text": " ".join(words),
            "page": page_num,
            "chunk_index": index,
            "word_count": len(words),
        }

    def _detect_section_header(self, line: str) -> bool:
        """Detect if a line is a section header"""
        line = line.strip()

        return (
            (line.isupper() and len(line) > 5)
            or bool(re.match(r"^\d+(\.\d+)*\s+[A-Z]", line))
            or bool(re.match(r"^(CHAPTER|SECTION|PART)\s+", line, re.I))
        )


chunker = SmartChunker(chunk_size=5, overlap=2, respect_paragraphs=True)

text = """
Hello world this

This is paragraph two with more words. Input Types: Requires an iterable; passing a non-iterable (like an integer or boolean) will raise a TypeError.

This is paragraph three.
"""

print(chunker.chunk(text, 1))
