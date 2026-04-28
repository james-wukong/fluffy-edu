class QualityFilter:
    def __init__(
        self,
        min_csat: float = 4.0,
        require_resolved: bool = True,
        min_answer_words: int = 20,
        max_answer_words: int = 500,
    ):
        self.min_csat = min_csat
        self.require_resolved = require_resolved
        self.min_answer_words = min_answer_words
        self.max_answer_words = max_answer_words

        self.stats = {
            "total": 0,
            "passed": 0,
            "failed_csat": 0,
            "failed_resolved": 0,
            "failed_length": 0,
            "failed_quality": 0,
        }

    def filter(self, logs: list[dict]) -> list[dict]:
        passed = []

        for log in logs:
            self.stats["total"] += 1
            result, reason = self.should_include(log)

            if result:
                passed.append(log)
                self.stats["passed"] += 1
            else:
                self.stats[f"failed_{reason}"] += 1

        self.print_stats()
        return passed

    def should_include(self, log: dict) -> tuple[bool, str]:
        # CSAT score gate
        csat = log.get("customer_satisfaction")
        if csat and float(csat) < self.min_csat:
            return False, "csat"

        # Resolution gate
        if self.require_resolved and not log.get("was_resolved", True):
            return False, "resolved"

        # Length gates
        answer_words = len(log.get("answer", "").split())
        if answer_words < self.min_answer_words:
            return False, "length"
        if answer_words > self.max_answer_words:
            return False, "length"

        # Quality: answer shouldn't just echo the question
        q_words = set(log.get("question", "").lower().split())
        a_words = set(log.get("answer", "").lower().split())
        overlap = len(q_words & a_words) / max(len(q_words), 1)
        if overlap > 0.8:
            return False, "quality"

        return True, "ok"

    def print_stats(self):
        s = self.stats
        pct = s["passed"] / max(s["total"], 1) * 100
        print("\n📊 Quality Filter Results:")
        print(f"   Total:          {s['total']}")
        print(f"   ✅ Passed:       {s['passed']} ({pct:.1f}%)")
        print(f"   ❌ Low CSAT:     {s['failed_csat']}")
        print(f"   ❌ Unresolved:   {s['failed_resolved']}")
        print(f"   ❌ Wrong length: {s['failed_length']}")
        print(f"   ❌ Low quality:  {s['failed_quality']}")


# quality_filter = QualityFilter(min_csat=4.0, require_resolved=True)
