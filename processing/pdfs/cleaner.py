import re
import unicodedata


class PDFTextCleaner:
    def clean(self, text: str) -> str:
        text = self._fix_encoding(text)
        text = self._remove_headers_footers(text)
        text = self._fix_hyphenation(text)
        text = self._normalize_whitespace(text)
        text = self._remove_boilerplate(text)
        text = self._fix_special_chars(text)
        return text.strip()

    def _fix_encoding(self, text: str) -> str:
        # Normalize unicode (fix mojibake)
        text = unicodedata.normalize("NFKD", text)
        # Remove non-printable control chars except newlines
        text = "".join(c for c in text if unicodedata.category(c) != "Cc" or c == "\n")
        return text

    def _remove_headers_footers(self, text: str) -> str:
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            # Skip page numbers: "Page 1 of 10", "- 5 -", "1"
            if re.match(r"^-?\s*\d+\s*-?$", line.strip()):
                continue
            if re.match(r"^page\s+\d+\s*(of\s+\d+)?$", line.strip(), re.I):
                continue
            # Skip very short repeated lines (likely headers/footers)
            if len(line.strip()) < 4:
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def _fix_hyphenation(self, text: str) -> str:
        # Fix words broken across lines: "impor-\ntant" → "important"
        return re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    def _normalize_whitespace(self, text: str) -> str:
        # Collapse multiple spaces
        text = re.sub(r" {2,}", " ", text)
        # Max 2 consecutive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove trailing spaces per line
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        return text

    def _remove_boilerplate(self, text: str) -> str:
        # Remove common boilerplate patterns
        patterns = [
            r"confidential.*?do not distribute",
            r"all rights reserved",
            r"copyright \d{4}.*?\n",
            r"this document is.*?purposes only",
            r"printed on \d{2}/\d{2}/\d{4}",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text

    def _fix_special_chars(self, text: str) -> str:
        replacements = {
            "\u2019": "'",  # Smart apostrophe
            "\u201c": '"',  # Smart quote open
            "\u201d": '"',  # Smart quote close
            "\u2013": "-",  # En dash
            "\u2014": "--",  # Em dash
            "\u00a0": " ",  # Non-breaking space
            "\u2022": "-",  # Bullet point
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text


# cleaner = PDFTextCleaner()
