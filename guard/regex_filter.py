import re
from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass
class RegexResult:
    is_safe: bool
    category: str | None = None
    matched_pattern: str | None = None

class RegexFilter:
    def __init__(self, rules_path: str):
        with open(rules_path) as f:
            raw = yaml.safe_load(f) or {}
        self._rules: dict[str, list[re.Pattern]] = {}
        for category, patterns in raw.items():
            self._rules[category] = [re.compile(p, re.IGNORECASE) for p in patterns]

    def check(self, prompt: str) -> RegexResult:
        for category, patterns in self._rules.items():
            for pattern in patterns:
                if pattern.search(prompt):
                    return RegexResult(is_safe=False, category=category, matched_pattern=pattern.pattern)
        return RegexResult(is_safe=True)
