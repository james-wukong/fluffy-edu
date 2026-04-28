import re

class SmartChunker:
    def __init__(
        self,
        chunk_size: int = 512,
        overlap: int = 64,
        respect_paragraphs: bool = True
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.respect_paragraphs = respect_paragraphs
    
    def chunk(self, text: str, page_num: int) -> list[dict]:
        if self.respect_paragraphs:
            return self._paragraph_aware_chunk(text, page_num)
        return self._fixed_size_chunk(text, page_num)
    
    def validate_chunk(self, chunk: dict) -> tuple[bool, str]:
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

    def _paragraph_aware_chunk(
        self, text: str, page_num: int
    ) -> list[dict]:
        """Respect paragraph boundaries — chunks make more sense"""
        
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current_chunk = []
        current_len = 0
        
        for para in paragraphs:
            para_words = len(para.split())
            
            # If adding this paragraph would exceed limit → save chunk
            if current_len + para_words > self.chunk_size and current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append({
                    "text": chunk_text,
                    "page": page_num,
                    "chunk_index": len(chunks),
                    "word_count": current_len
                })
                
                # Overlap: keep last paragraph in next chunk
                overlap_paras = current_chunk[-1:] if self.overlap else []
                current_chunk = overlap_paras
                current_len = len(" ".join(overlap_paras).split())
            
            current_chunk.append(para)
            current_len += para_words
        
        # Save remaining
        if current_chunk:
            chunks.append({
                "text": "\n\n".join(current_chunk),
                "page": page_num,
                "chunk_index": len(chunks),
                "word_count": current_len
            })
        
        return chunks
    
    def _detect_section_header(self, line: str) -> bool:
        """Detect if a line is a section header"""
        # All caps, or starts with number like "1.2 Section Name"
        return (
            line.isupper() and len(line) > 5 or
            bool(re.match(r"^\d+\.?\d*\s+[A-Z]", line)) or
            bool(re.match(r"^(CHAPTER|SECTION|PART)\s+", line, re.I))
        )

// chunker = SmartChunker(chunk_size=512, overlap=64)