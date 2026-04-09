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
    def __init__(self, regex_filter: RegexFilter, llm_filter: LlmFilter | None = None, db: Database | None = None):
        self._regex = regex_filter
        self._llm = llm_filter
        self._db = db

    async def check(self, prompt: str, agent_name: str) -> GuardVerdict:
        regex_result = self._regex.check(prompt)
        if not regex_result.is_safe:
            verdict = GuardVerdict(blocked=True, reason=f"regex:{regex_result.category}", prompt=prompt, agent=agent_name)
            await self._log(verdict)
            return verdict
        if self._llm:
            llm_result = await self._llm.check(prompt)
            if llm_result == LlmResult.DANGEROUS:
                verdict = GuardVerdict(blocked=True, reason=f"llm:{llm_result.value}", prompt=prompt, agent=agent_name)
                await self._log(verdict)
                return verdict
            if llm_result == LlmResult.SUSPICIOUS:
                verdict = GuardVerdict(suspicious=True, reason=f"llm:{llm_result.value}", prompt=prompt, agent=agent_name)
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
                "INSERT INTO guard_logs (prompt, agent_name, final_result) VALUES (?, ?, ?)",
                (verdict.prompt, verdict.agent, final),
            )
        except Exception as e:
            logger.warning(f"Failed to log guard verdict: {e}")
