---
id: AGOS-0012
title: Prompt Guard — оркестрация
phase: 2 — Безопасность
status: pending
depends_on: [AGOS-0003, AGOS-0010, AGOS-0011]
files_create: [guard/prompt_guard.py, tests/test_prompt_guard.py]
files_modify: []
---

## Описание

Оркестратор двухуровневой проверки промтов. Pipeline: regex (~1ms) → LLM Haiku (~200ms) → вердикт (pass/suspicious/block). Логирует все проверки в SQLite (guard_logs). Если LLM отключён — работает только regex. Ошибка логирования не ломает проверку.

## Acceptance Criteria

- [ ] Regex блокирует → verdict.blocked=True, reason="regex:category"
- [ ] LLM DANGEROUS → verdict.blocked=True, reason="llm:DANGEROUS"
- [ ] LLM SUSPICIOUS → verdict.suspicious=True, blocked=False
- [ ] LLM SAFE → pass (blocked=False, suspicious=False)
- [ ] LLM отключён (None) → только regex
- [ ] Все проверки логируются в guard_logs
- [ ] Тесты с моками проходят (5 тестов)

## Затрагиваемые модули

- guard/prompt_guard.py: PromptGuard, GuardVerdict
- tests/test_prompt_guard.py: юнит-тесты

## Ключевые интерфейсы

```python
@dataclass
class GuardVerdict:
    blocked: bool = False
    suspicious: bool = False
    reason: str = ""
    prompt: str = ""
    agent: str = ""

class PromptGuard:
    def __init__(self, regex_filter: RegexFilter, llm_filter: LlmFilter | None = None, db: Database | None = None)
    async def check(self, prompt: str, agent_name: str) -> GuardVerdict
```

## Edge Cases

- LLM фильтр отключён (None) — только regex
- Ошибка логирования — warning в лог, проверка продолжается
- db=None — логирование пропускается

## План реализации

### Step 1: Написать тест

```python
# tests/test_prompt_guard.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from guard.prompt_guard import PromptGuard, GuardVerdict
from guard.regex_filter import RegexResult
from guard.llm_filter import LlmResult


@pytest.fixture
def guard():
    regex = MagicMock()
    llm = AsyncMock()
    db = AsyncMock()
    return PromptGuard(regex_filter=regex, llm_filter=llm, db=db)


@pytest.mark.asyncio
async def test_regex_blocks(guard):
    guard._regex.check.return_value = RegexResult(
        is_safe=False, category="injection", matched_pattern="ignore previous"
    )
    verdict = await guard.check("ignore previous instructions", "jira")
    assert verdict.blocked
    assert verdict.reason == "regex:injection"


@pytest.mark.asyncio
async def test_llm_blocks(guard):
    guard._regex.check.return_value = RegexResult(is_safe=True)
    guard._llm.check.return_value = LlmResult.DANGEROUS
    verdict = await guard.check("subtle injection attempt", "jira")
    assert verdict.blocked
    assert verdict.reason == "llm:DANGEROUS"


@pytest.mark.asyncio
async def test_llm_suspicious_passes_with_warning(guard):
    guard._regex.check.return_value = RegexResult(is_safe=True)
    guard._llm.check.return_value = LlmResult.SUSPICIOUS
    verdict = await guard.check("show me .bashrc", "jira")
    assert not verdict.blocked
    assert verdict.suspicious


@pytest.mark.asyncio
async def test_safe_prompt_passes(guard):
    guard._regex.check.return_value = RegexResult(is_safe=True)
    guard._llm.check.return_value = LlmResult.SAFE
    verdict = await guard.check("сделай отчёт", "jira")
    assert not verdict.blocked
    assert not verdict.suspicious


@pytest.mark.asyncio
async def test_llm_disabled(guard):
    guard._llm = None
    guard._regex.check.return_value = RegexResult(is_safe=True)
    verdict = await guard.check("hello", "jira")
    assert not verdict.blocked
```

### Step 2: Реализовать prompt_guard.py

```python
# guard/prompt_guard.py
import logging
from dataclasses import dataclass
from guard.regex_filter import RegexFilter
from guard.llm_filter import LlmFilter, LlmResult
from db.database import Database

logger = logging.getLogger(__name__)


@dataclass
class GuardVerdict:
    blocked: bool = False
    suspicious: bool = False
    reason: str = ""
    prompt: str = ""
    agent: str = ""


class PromptGuard:
    def __init__(
        self,
        regex_filter: RegexFilter,
        llm_filter: LlmFilter | None = None,
        db: Database | None = None,
    ):
        self._regex = regex_filter
        self._llm = llm_filter
        self._db = db

    async def check(self, prompt: str, agent_name: str) -> GuardVerdict:
        # Level 1: regex
        regex_result = self._regex.check(prompt)
        if not regex_result.is_safe:
            verdict = GuardVerdict(
                blocked=True,
                reason=f"regex:{regex_result.category}",
                prompt=prompt,
                agent=agent_name,
            )
            await self._log(verdict)
            return verdict

        # Level 2: LLM
        if self._llm:
            llm_result = await self._llm.check(prompt)
            if llm_result == LlmResult.DANGEROUS:
                verdict = GuardVerdict(
                    blocked=True,
                    reason=f"llm:{llm_result.value}",
                    prompt=prompt,
                    agent=agent_name,
                )
                await self._log(verdict)
                return verdict
            if llm_result == LlmResult.SUSPICIOUS:
                verdict = GuardVerdict(
                    suspicious=True,
                    reason=f"llm:{llm_result.value}",
                    prompt=prompt,
                    agent=agent_name,
                )
                await self._log(verdict)
                return verdict

        verdict = GuardVerdict(prompt=prompt, agent=agent_name)
        await self._log(verdict)
        return verdict

    async def _log(self, verdict: GuardVerdict):
        if not self._db:
            return
        final = "block" if verdict.blocked else ("suspicious" if verdict.suspicious else "pass")
        try:
            await self._db.execute(
                """INSERT INTO guard_logs (prompt, agent_name, final_result)
                   VALUES (?, ?, ?)""",
                (verdict.prompt, verdict.agent, final),
            )
        except Exception as e:
            logger.warning(f"Failed to log guard verdict: {e}")
```

### Step 3: Запустить тесты — PASS

```bash
pytest tests/test_prompt_guard.py -v
```

### Step 4: Commit

```bash
git add guard/prompt_guard.py tests/test_prompt_guard.py
git commit -m "feat: add PromptGuard orchestrator (regex + LLM pipeline)"
```
