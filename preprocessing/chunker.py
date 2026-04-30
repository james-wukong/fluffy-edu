import re

from preprocessing.pdfs.extractor import PageResult
from preprocessing.schema import ChunkMetadata, ChunkResult, MetaData


class SmartChunker:
    def __init__(
        self,
        chunk_size: int = 512,
        overlap: int = 64,
        respect_paragraphs: bool = True,
        language: str = "en",  # ← new: "en" or "zh"
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
        self.language = language

        # Chinese sentence boundaries
        self.zh_sentence_endings = re.compile(r"[。！？…\n]")

    def chunk(self, page_result: PageResult) -> list[ChunkResult]:
        text = page_result["text"].strip()
        if not text:
            return []

        if self.language == "zh":
            return self._chinese_chunk(text, page_result["metadata"])

        if self.respect_paragraphs:
            return self._paragraph_aware_chunk(text, page_result["metadata"])
        return self._fixed_size_chunk(text, page_result["metadata"])

    # ── Chinese chunking (character-based) ────────────────────

    def _chinese_chunk(self, text: str, metadata: MetaData) -> list[ChunkResult]:
        """
        Character-based chunking for Chinese text.
        ~500 Chinese characters ≈ ~512 tokens.
        Respects sentence boundaries (。！？) instead of paragraphs.
        """
        sentences = self._split_chinese_sentences(text)
        chunks: list[ChunkResult] = []
        current_sents: list[str] = []
        current_len = 0

        for sentence in sentences:
            sent_len = len(sentence)

            # Single sentence exceeds chunk_size — force split it
            if sent_len > self.chunk_size:
                if current_sents:
                    chunks.append(
                        self._make_chunk(
                            list("".join(current_sents)),
                            metadata,
                            len(chunks),
                            use_chars=True,
                        )
                    )
                    current_sents = current_sents[-1:]
                    current_len = len(current_sents[0]) if current_sents else 0

                # Split the oversized sentence by character windows
                for i in range(0, sent_len, self.chunk_size - self.overlap):
                    window = sentence[i : i + self.chunk_size]
                    chunks.append(
                        self._make_chunk(
                            list(window), metadata, len(chunks), use_chars=True
                        )
                    )
                continue

            if current_len + sent_len > self.chunk_size and current_sents:
                chunks.append(
                    self._make_chunk(
                        list("".join(current_sents)),
                        metadata,
                        len(chunks),
                        use_chars=True,
                    )
                )
                # Overlap: keep last sentence
                current_sents = current_sents[-1:] if self.overlap else []
                current_len = len(current_sents[0]) if current_sents else 0

            current_sents.append(sentence)
            current_len += sent_len

        if current_sents:
            chunks.append(
                self._make_chunk(
                    list("".join(current_sents)),
                    metadata,
                    len(chunks),
                    use_chars=True,
                )
            )

        return chunks

    def _split_chinese_sentences(self, text: str) -> list[str]:
        """Split on Chinese sentence-ending punctuation"""
        parts = self.zh_sentence_endings.split(text)
        endings = self.zh_sentence_endings.findall(text)

        sentences = []
        for i, part in enumerate(parts):
            if part.strip():
                ending = endings[i] if i < len(endings) else ""
                sentences.append(part.strip() + ending)

        return sentences

    # ── English chunking (word-based) ─────────────────────────

    def _fixed_size_chunk(self, text: str, metadata: MetaData) -> list[ChunkResult]:
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
        self, text: str, metadata: MetaData
    ) -> list[ChunkResult]:
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
                        self._make_chunk(current_words, metadata, len(chunks))
                    )
                    current_words = current_words[-self.overlap :]

                large_chunks = self._fixed_size_chunk(para, metadata)
                for item in large_chunks:
                    chunk_meta: ChunkMetadata = {
                        "chunk_index": len(chunks),
                        "word_count": len(item["text"]),
                    }
                    item["metadata"]["chunk_meta"] = chunk_meta
                    chunks.append(item)

                current_words = []
                continue

            if len(current_words) + len(para_words) > self.chunk_size:
                chunks.append(self._make_chunk(current_words, metadata, len(chunks)))
                current_words = current_words[-self.overlap :]

            current_words.extend(para_words)

        if current_words:
            chunks.append(self._make_chunk(current_words, metadata, len(chunks)))

        return chunks

    def _make_chunk(
        self,
        words: list[str],
        metadata: MetaData,
        index: int,
        use_chars: bool = False,
    ) -> ChunkResult:
        text = ("" if use_chars else " ").join(words)
        chunk_meta: ChunkMetadata = {
            "chunk_index": index,
            "word_count": len(words),
        }
        metadata["chunk_meta"] = chunk_meta
        return {
            "text": text,
            "metadata": metadata,
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


# if __name__ == "__main__":
#     chunker = SmartChunker(chunk_size=512, overlap=64)

#     text: PageResult = {
#         "text": """
# Hello world this

# This is paragraph two with more words. Input Types: Requires an iterable; passing a non-iterable (like an integer or boolean) will raise a TypeError.

# This is paragraph three.
# """,
#         "metadata": {"page": 1},
#     }

#     print(chunker.chunk(text))
