import json
import logging
import os
from pathlib import Path
from core.models import AgentRuntime, AgentStatus, ModelBinding, ModelProvider
from db.database import Database
from runtime.base import BaseRuntime
from memory.memory import MemorySystem

logger = logging.getLogger(__name__)


class AgentManager:
    def __init__(
        self,
        db: Database,
        tmux_runtime: BaseRuntime | None = None,
        docker_runtime: BaseRuntime | None = None,
        memory: MemorySystem | None = None,
        model_providers: dict[str, dict] | None = None,
    ):
        self.db = db
        self._tmux = tmux_runtime
        self._docker = docker_runtime
        self._memory = memory
        self._model_providers = model_providers or {}

    def _resolve_binding(self, provider_name: str) -> ModelBinding:
        if not provider_name:
            return ModelBinding()
        raw = self._model_providers.get(provider_name)
        if raw is None:
            raise ValueError(f"Unknown model provider '{provider_name}'")
        provider_value = raw.get("provider", ModelProvider.CLAUDE_SUBSCRIPTION.value)
        return ModelBinding(
            provider=ModelProvider(provider_value),
            model_name=raw.get("model_name", ""),
            base_url=raw.get("base_url", ""),
            api_key_env=raw.get("api_key_env", ""),
            small_fast_model=raw.get("small_fast_model", ""),
        )

    def _build_agent_env(self, binding: ModelBinding) -> dict[str, str]:
        if binding.provider == ModelProvider.CLAUDE_SUBSCRIPTION:
            return {}
        if not binding.api_key_env:
            raise ValueError("api_key_env is required for non-subscription providers")
        api_key = os.environ.get(binding.api_key_env)
        if not api_key:
            raise ValueError(f"Environment variable '{binding.api_key_env}' is not set")
        if binding.provider == ModelProvider.ANTHROPIC_API:
            env = {"ANTHROPIC_API_KEY": api_key}
            if binding.model_name:
                env["ANTHROPIC_MODEL"] = binding.model_name
            return env
        if binding.provider == ModelProvider.ANTHROPIC_COMPATIBLE:
            if not binding.base_url:
                raise ValueError("base_url is required for anthropic_compatible provider")
            env = {
                "ANTHROPIC_BASE_URL": binding.base_url,
                "ANTHROPIC_AUTH_TOKEN": api_key,
            }
            if binding.model_name:
                env["ANTHROPIC_MODEL"] = binding.model_name
            if binding.small_fast_model:
                env["ANTHROPIC_SMALL_FAST_MODEL"] = binding.small_fast_model
            return env
        return {}

    def build_llm_credentials(self, provider_name: str) -> dict:
        """Вернуть параметры для Python-SDK клиента (guard, вспомогательные тулы).

        В отличие от `_build_agent_env` — не выставляет env для дочернего процесса,
        а возвращает явные поля, которые SDK принимает в конструкторе. Subscription
        не поддерживается: Python-SDK Anthropic требует API-ключ, `claude login`
        к нему не применим.
        """
        binding = self._resolve_binding(provider_name)
        if binding.provider == ModelProvider.CLAUDE_SUBSCRIPTION:
            raise ValueError(
                "claude_subscription provider is CLI-only and cannot be used for "
                "Python SDK clients (e.g. Prompt Guard). Use anthropic_api or "
                "anthropic_compatible instead."
            )
        if not binding.api_key_env:
            raise ValueError("api_key_env is required for SDK provider")
        api_key = os.environ.get(binding.api_key_env)
        if not api_key:
            raise ValueError(f"Environment variable '{binding.api_key_env}' is not set")
        if binding.provider == ModelProvider.ANTHROPIC_COMPATIBLE and not binding.base_url:
            raise ValueError("base_url is required for anthropic_compatible provider")
        return {
            "api_key": api_key,
            "base_url": binding.base_url,
            "model_name": binding.model_name,
        }

    def validate_provider(self, provider_name: str, runtime: AgentRuntime) -> None:
        """Проверить провайдера на старте — до запуска бота.

        Для не-подписочных провайдеров вызывает `_build_agent_env` — тот падает
        с понятной ошибкой, если не хватает env-переменной или base_url. Для
        подписочного провайдера на host-runtime предупреждает, если `~/.claude`
        отсутствует (не фатально — пользователь может залогиниться после).
        """
        binding = self._resolve_binding(provider_name)
        if binding.provider == ModelProvider.CLAUDE_SUBSCRIPTION:
            if runtime == AgentRuntime.HOST:
                claude_dir = Path.home() / ".claude"
                if not claude_dir.exists():
                    logger.warning(
                        "Claude Code CLI не залогинен (%s не существует). "
                        "Запусти `claude login` до отправки промтов мастеру.",
                        claude_dir,
                    )
            return
        self._build_agent_env(binding)

    def apply_provider_env(self, name: str, provider_name: str, runtime: AgentRuntime) -> None:
        """Переэкспортировать env провайдера в уже существующий runtime агента.

        Нужно при рестарте AG-OS: мастер-окно tmux переживает рестарт, но после
        изменения конфига env в окне становится устаревшим. Для host-runtime —
        делает `export KEY=VALUE` в окне. Для docker-runtime — no-op (у запущенного
        контейнера env не меняется, надо пересоздавать агента).
        """
        binding = self._resolve_binding(provider_name)
        env = self._build_agent_env(binding)
        if runtime != AgentRuntime.HOST:
            if env:
                logger.warning(
                    "Agent '%s' running in docker runtime — env re-apply skipped. "
                    "Recreate the container to change provider.",
                    name,
                )
            return
        if not env:
            return
        rt = self._get_runtime(runtime)
        apply = getattr(rt, "apply_env", None)
        if apply is None:
            return
        apply(name, env)
        logger.info("Re-applied provider '%s' env to agent '%s'", provider_name, name)

    async def ensure_runtime(self, agent_row: dict) -> bool:
        """Гарантировать что runtime-артефакт агента (tmux-окно / docker-контейнер) жив.

        Вызывается из bootstrap для каждой строки БД: если окно/контейнер был
        убит между рестартами AG-OS, пересоздаём его с теми же env-переменными
        провайдера, что хранятся в config JSON записи агента. DB-строку не
        трогаем — только runtime.

        Возвращает True если был сделан resurrect (runtime пересоздан), False
        если артефакт уже был живым.
        """
        name = agent_row["name"]
        runtime = AgentRuntime(agent_row["runtime"])
        rt = self._get_runtime(runtime)
        if rt.agent_exists(name):
            return False
        stored_config = json.loads(agent_row.get("config") or "{}")
        provider_name = stored_config.get("model_provider", "")
        binding = self._resolve_binding(provider_name)
        env = self._build_agent_env(binding)
        rt.create_agent(name, env=env)
        logger.info("Resurrected runtime for agent '%s' (%s)", name, runtime.value)
        return True

    def _get_runtime(self, runtime: AgentRuntime) -> BaseRuntime:
        if runtime == AgentRuntime.HOST:
            if not self._tmux:
                raise RuntimeError("tmux runtime not configured")
            return self._tmux
        if not self._docker:
            raise RuntimeError("docker runtime not configured")
        return self._docker

    async def create_agent(
        self,
        name: str,
        model: str,
        runtime: AgentRuntime,
        agent_type: str = "dynamic",
        config: dict | None = None,
        provider_name: str = "",
    ) -> dict:
        existing = await self.db.fetch_one("SELECT id FROM agents WHERE name = ?", (name,))
        if existing:
            raise ValueError(f"Agent '{name}' already exists")
        binding = self._resolve_binding(provider_name)
        env = self._build_agent_env(binding)
        rt = self._get_runtime(runtime)
        rt.create_agent(name, env=env)
        stored_config = dict(config or {})
        if provider_name:
            stored_config["model_provider"] = provider_name
        await self.db.execute(
            "INSERT INTO agents (name, model, runtime, type, status, tmux_window, config) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, model, runtime.value, agent_type, AgentStatus.IDLE.value, name if runtime == AgentRuntime.HOST else "", json.dumps(stored_config)),
        )
        return await self.get_agent(name)

    async def destroy_agent(self, name: str) -> None:
        agent = await self.get_agent(name)
        if not agent:
            raise ValueError(f"Agent '{name}' not found")
        rt = self._get_runtime(AgentRuntime(agent["runtime"]))
        rt.destroy_agent(name)
        await self.db.execute("DELETE FROM agents WHERE name = ?", (name,))

    async def send_prompt(self, name: str, prompt: str) -> None:
        agent = await self.get_agent(name)
        if not agent:
            raise ValueError(f"Agent '{name}' not found")
        rt = self._get_runtime(AgentRuntime(agent["runtime"]))
        final_prompt = prompt
        if self._memory:
            context = await self._memory.get_context(name)
            if context:
                memory_lines = [f"[Memory] {r['key']}: {r['value']}" for r in context]
                final_prompt = "\n".join(memory_lines) + "\n\n" + prompt
        rt.send_prompt(name, final_prompt)
        await self.db.execute("UPDATE agents SET status = ?, current_task = ? WHERE name = ?", (AgentStatus.WORKING.value, prompt, name))

    async def read_output(self, name: str, lines: int = 50) -> str:
        agent = await self.get_agent(name)
        if not agent:
            raise ValueError(f"Agent '{name}' not found")
        rt = self._get_runtime(AgentRuntime(agent["runtime"]))
        return rt.read_output(name, lines)

    async def get_agent(self, name: str) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM agents WHERE name = ?", (name,))

    async def list_agents(self) -> list[dict]:
        return await self.db.fetch_all("SELECT * FROM agents ORDER BY name")

    async def update_status(self, name: str, status: AgentStatus) -> None:
        await self.db.execute("UPDATE agents SET status = ? WHERE name = ?", (status.value, name))
