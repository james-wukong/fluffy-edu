import re

from better_profanity import Profanity  # pip install better-profanity

profanity = Profanity()


class ChatLogCleaner:
    # PII patterns
    PII_PATTERNS = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\b(\+?1?\s?)?(\(?\d{3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}\b",
        "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "ip_address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        "date_of_birth": r"\b(DOB|date of birth)[:\s]+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    }

    def clean_conversation(self, log: dict) -> dict | None:
        question = log.get("question", "").strip()
        answer = log.get("answer", "").strip()

        # Skip empty
        if not question or not answer:
            return None

        # Remove PII
        question = self.remove_pii(question)
        answer = self.remove_pii(answer)

        # Remove profanity (optional — depends on use case)
        if profanity.contains_profanity(question + answer):
            question = profanity.censor(question)
            answer = profanity.censor(answer)

        # Clean formatting
        question = self.clean_text(question)
        answer = self.clean_text(answer)

        # Validate lengths
        if len(question.split()) < 3 or len(answer.split()) < 5:
            return None
        if len(answer.split()) > 1000:
            answer = " ".join(answer.split()[:1000]) + "..."

        log["question"] = question
        log["answer"] = answer
        return log

    def remove_pii(self, text: str) -> str:
        for pii_type, pattern in self.PII_PATTERNS.items():
            replacement = f"[{pii_type.upper()}]"
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def clean_text(self, text: str) -> str:
        # Remove URLs
        text = re.sub(r"https?://\S+", "[URL]", text)
        # Fix spacing
        text = re.sub(r" {2,}", " ", text)
        # Fix repeated punctuation
        text = re.sub(r"([!?.]){3,}", r"\1\1", text)
        # Fix newlines
        text = re.sub(r"\n{2,}", "\n", text)
        return text.strip()


# cleaner = ChatLogCleaner()
