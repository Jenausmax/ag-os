from abc import ABC, abstractmethod


class BaseRuntime(ABC):
    @abstractmethod
    def create_agent(self, name: str, command: str = "") -> str:
        """Создать агента, вернуть идентификатор."""

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
