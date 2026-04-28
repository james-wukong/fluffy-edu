class AutoTagger:
    # Rule-based tagging (fast, no model needed)
    TOPIC_RULES = {
        "billing": ["invoice", "payment", "charge", "refund", "bill", "price"],
        "returns": ["return", "exchange", "refund", "ship back", "send back"],
        "technical": ["error", "bug", "crash", "not working", "broken", "issue"],
        "account": ["login", "password", "account", "sign in", "access"],
        "shipping": ["delivery", "tracking", "shipped", "package", "courier"],
        "product_info": [
            "features",
            "specification",
            "does it",
            "can it",
            "compatible",
        ],
        "cancellation": ["cancel", "terminate", "stop", "unsubscribe", "end"],
    }

    INTENT_RULES = {
        "complaint": ["not working", "broken", "terrible", "awful", "disappointed"],
        "question": ["how do", "what is", "where can", "when will", "can you"],
        "request": ["please", "i need", "i want", "i would like", "can you"],
        "feedback": ["suggestion", "feedback", "idea", "improve", "recommend"],
        "escalation": ["manager", "supervisor", "escalate", "unacceptable"],
    }

    def tag(self, log: dict) -> dict:
        text = (log.get("question", "") + " " + log.get("answer", "")).lower()

        log["topic"] = self._match_rules(text, self.TOPIC_RULES)
        log["intent"] = self._match_rules(text, self.INTENT_RULES)
        log["sentiment"] = self._simple_sentiment(text)

        return log

    def _match_rules(self, text: str, rules: dict) -> str:
        scores = {}
        for category, keywords in rules.items():
            scores[category] = sum(1 for kw in keywords if kw in text)

        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "other"

    def _simple_sentiment(self, text: str) -> str:
        positive = ["thank", "great", "excellent", "helpful", "resolved", "perfect"]
        negative = ["angry", "frustrated", "terrible", "worst", "useless", "awful"]

        pos = sum(1 for w in positive if w in text)
        neg = sum(1 for w in negative if w in text)

        if pos > neg:
            return "positive"
        if neg > pos:
            return "negative"
        return "neutral"


tagger = AutoTagger()
