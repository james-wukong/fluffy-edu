import csv
import json
from pathlib import Path


class ChatLogParser:
    def parse(self, file_path: str) -> list[dict]:
        ext = Path(file_path).suffix.lower()

        if ext == ".json":
            return self._parse_json(file_path)
        elif ext == ".csv":
            return self._parse_csv(file_path)
        elif ext == ".txt":
            return self._parse_txt(file_path)
        else:
            raise ValueError(f"Unsupported format: {ext}")

    def _parse_json(self, path: str) -> list[dict]:
        with open(path) as f:
            data = json.load(f)
        # Handle both list and dict formats
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("conversations", data.get("logs", []))

    def _parse_csv(self, path: str) -> list[dict]:
        logs = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                logs.append(dict(row))
        return logs

    def _parse_txt(self, path: str) -> list[dict]:
        """Parse turn-based text chat format:
        User: ...
        Agent: ...
        """
        logs = []
        current = {"question": "", "answer": ""}

        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.lower().startswith("user:"):
                    if current["question"]:
                        logs.append(current.copy())
                    current = {"question": line[5:].strip(), "answer": ""}
                elif line.lower().startswith(("agent:", "assistant:", "bot:")):
                    current["answer"] = line.split(":", 1)[1].strip()

        if current["question"]:
            logs.append(current)

        return logs
