# processing/cleaner.py

import re
import unicodedata


class TextCleaner:
    """
    Unified cleaner for both English and Chinese text.
    Language-specific steps are gated behind the language parameter.
    """

    # ── PII Personally Identifiable Information ───────────────
    PII_PATTERNS: dict[str, str] = {
        # English
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "phone_us": r"\b(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        # Chinese
        "id_card": r"\d{17}[\dXx]",
        "phone_cn": r"1[3-9]\d{9}",
        "wechat": r"微信[号:：\s]*[\w\-]{6,20}",
        "bank_card": r"\b\d{16,19}\b",
    }

    # ── Full-width → half-width punctuation (Chinese) ─────────
    ZH_PUNCTUATION_MAP: dict[str, str] = {
        "，": ",",
        "。": ".",
        "！": "!",
        "？": "?",
        "；": ";",
        "：": ":",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "\u3000": " ",
        "\uff0d": "-",
        "\u2014": "--",
        "\u2013": "-",
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u00a0": " ",
    }

    # ── Smart quotes / special chars (English) ────────────────
    EN_CHAR_MAP: dict[str, str] = {
        "\u2019": "'",  # Smart apostrophe
        "\u201c": '"',  # Smart quote open
        "\u201d": '"',  # Smart quote close
        "\u2013": "-",  # En dash
        "\u2014": "--",  # Em dash
        "\u00a0": " ",  # Non-breaking space
        "\u2022": "-",  # Bullet point
    }

    # ── Boilerplate patterns (English) ────────────────────────
    BOILERPLATE_PATTERNS: list[str] = [
        r"confidential.*?do not distribute",
        r"all rights reserved",
        r"copyright \d{4}.*?\n",
        r"this document is.*?purposes only",
        r"printed on \d{2}/\d{2}/\d{4}",
    ]

    def clean(self, text: str, language: str = "zh") -> str:
        """
        language: "en" for English, "zh" for Chinese
        """
        # ── Shared steps (run for both languages) ─────────────
        text = self._normalize_unicode(text)
        text = self._remove_headers_footers(text)
        text = self._remove_pii(text, language)
        text = self._normalize_whitespace(text, language)

        # ── English-only steps ────────────────────────────────
        if language == "en":
            text = self._fix_hyphenation(text)
            text = self._remove_boilerplate(text)
            text = self._fix_en_special_chars(text)

        # ── Chinese-only steps ────────────────────────────────
        if language == "zh":
            text = self._normalize_zh_punctuation(text)
            text = self._remove_zh_noise(text)

        return text.strip()

    # ── Shared steps ──────────────────────────────────────────

    def _normalize_unicode(self, text: str) -> str:
        # NFKC covers both mojibake fix and full-width → half-width
        text = unicodedata.normalize("NFKC", text)
        # Remove non-printable control chars except newlines
        text = "".join(c for c in text if unicodedata.category(c) != "Cc" or c == "\n")
        return text

    def _remove_headers_footers(self, text: str) -> str:
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            # Page numbers: "1", "- 5 -", "Page 3 of 10", "第3页"
            if re.match(r"^-?\s*\d+\s*-?$", stripped):
                continue
            if re.match(r"^page\s+\d+\s*(of\s+\d+)?$", stripped, re.I):
                continue
            if re.match(r"^第\s*\d+\s*页$", stripped):
                continue
            # Very short lines are usually artefacts
            if len(stripped) < 4:
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def _remove_pii(self, text: str, language: str) -> str:
        # English PII always removed
        en_keys = {"email", "phone_us", "ssn"}
        # Chinese PII only removed for Chinese docs
        zh_keys = {"id_card", "phone_cn", "wechat", "bank_card"}

        for key, pattern in self.PII_PATTERNS.items():
            if key in en_keys or (key in zh_keys and language == "zh"):
                text = re.sub(
                    pattern,
                    f"[{key.upper()}]",
                    text,
                    flags=re.IGNORECASE,
                )
        return text

    def _normalize_whitespace(self, text: str, language: str) -> str:
        if language == "zh":
            # Remove spaces between Chinese characters
            # but keep spaces around English/numbers within Chinese text
            text = re.sub(r"(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])", "", text)
        # Shared: collapse multiple spaces
        text = re.sub(r" {2,}", " ", text)
        # Max two consecutive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Trailing spaces per line
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        return text

    # ── English-only steps ────────────────────────────────────

    def _fix_hyphenation(self, text: str) -> str:
        # "impor-\ntant" → "important"
        return re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    def _remove_boilerplate(self, text: str) -> str:
        for pattern in self.BOILERPLATE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text

    def _fix_en_special_chars(self, text: str) -> str:
        for old, new in self.EN_CHAR_MAP.items():
            text = text.replace(old, new)
        return text

    # ── Chinese-only steps ────────────────────────────────────

    def _normalize_zh_punctuation(self, text: str) -> str:
        for full, half in self.ZH_PUNCTUATION_MAP.items():
            text = text.replace(full, half)
        return text

    def _remove_zh_noise(self, text: str) -> str:
        # Repeated Chinese characters — OCR or spam artefact
        text = re.sub(r"([\u4e00-\u9fff])\1{4,}", r"\1\1", text)
        # Emoji
        text = re.sub(r"[\U00010000-\U0010ffff]", "", text, flags=re.UNICODE)
        # Excessive punctuation
        text = re.sub(r"[,，.。!！?？]{3,}", ".", text)
        return text
