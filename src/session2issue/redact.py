"""Best-effort redaction for a report that must still be reviewed by a person."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}=?=?")),
    ("github_token", re.compile(r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{16,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b")),
    ("credential_assignment", re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password|passwd)['\"]?\s*[:=]\s*['\"]?[^\s'\",;]{8,}['\"]?")),
    ("credential_url", re.compile(r"(?i)\bhttps?://[^\s/@:]+:[^\s/@]+@")),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("home_path", re.compile(r"(?i)\b[A-Z]:(?:\\+|/)Users(?:\\+|/)[^\\/\s\"']+|/home/[^/\s\"']+|/Users/[^/\s\"']+")),
)


@dataclass(slots=True)
class Redactor:
    counts: dict[str, int] = field(default_factory=dict)

    def clean(self, text: str) -> str:
        # Normalize terminal styling before matching credentials, then clip at the caller.
        result = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        result = "".join(char for char in result if char in "\n\t" or not unicodedata.category(char).startswith("C"))
        for label, pattern in _RULES:
            replacement = "<HOME>" if label == "home_path" else f"[REDACTED:{label}]"
            result, count = pattern.subn(replacement, result)
            if count:
                self.counts[label] = self.counts.get(label, 0) + count
        return result

    @property
    def total(self) -> int:
        return sum(self.counts.values())
