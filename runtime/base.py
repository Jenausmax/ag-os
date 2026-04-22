from abc import ABC, abstractmethod


class BaseRuntime(ABC):
    @abstractmethod
    def create_agent(self, name: str, command: str = "", env: dict[str, str] | None = None) -> str:
        """Создать агента, вернуть идентификатор.

        ``env`` — переменные окружения агента (для перенаправления Claude Code CLI
        на альтернативный API через ANTHROPIC_BASE_URL и т.п.).
        """

    @abstractmethod
    def destroy_agent(self, name: str) -> None:
        """Остановить и удалить агента."""

    @abstractmethod
    def send_prompt(self, name: str, prompt: str) -> None:
        """Отправить промт агенту."""

    @abstractmethod
    def read_output(self, name: str, lines: int = 50) -> str:
        """Прочитать последний вывод агента."""

    @abstractmethod
    def list_agents(self) -> list[str]:
        """Список имён запущенных агентов."""

    @abstractmethod
    def agent_exists(self, name: str) -> bool:
        """Проверить существует ли агент."""

    @abstractmethod
    def clear_context(self, name: str) -> None:
        """Сбросить REPL-контекст агента. No-op, если runtime stateless (Docker batch)."""
