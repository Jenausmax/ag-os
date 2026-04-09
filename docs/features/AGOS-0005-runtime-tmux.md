---
id: AGOS-0005
title: Runtime — абстракция и tmux-реализация
phase: 1 — MVP
status: pending
depends_on: [AGOS-0002]
files_create: [runtime/base.py, runtime/tmux_runtime.py, tests/test_tmux_runtime.py]
files_modify: []
---

## Описание

Абстрактный BaseRuntime (ABC) определяет контракт для runtime-слоя: create, destroy, send_prompt, read_output, list, exists. TmuxRuntime — первая реализация через libtmux. Одна tmux-сессия `ag-os`, каждый агент = отдельное окно. Отправка промтов через send_keys, чтение вывода через capture_pane.

## Acceptance Criteria

- [ ] BaseRuntime определяет 6 абстрактных методов
- [ ] TmuxRuntime создаёт сессию если не существует, подключается к существующей
- [ ] create_agent создаёт окно, отправляет command если задан
- [ ] destroy_agent убивает окно
- [ ] send_prompt отправляет через send_keys
- [ ] read_output возвращает join capture_pane
- [ ] list_agents возвращает имена окон
- [ ] Тесты с моками проходят (6 тестов)

## Затрагиваемые модули

- runtime/base.py: ABC BaseRuntime
- runtime/tmux_runtime.py: TmuxRuntime
- tests/test_tmux_runtime.py: юнит-тесты с моками libtmux

## Ключевые интерфейсы

```python
class BaseRuntime(ABC):
    def create_agent(self, name: str, command: str = "") -> str
    def destroy_agent(self, name: str) -> None
    def send_prompt(self, name: str, prompt: str) -> None
    def read_output(self, name: str, lines: int = 50) -> str
    def list_agents(self) -> list[str]
    def agent_exists(self, name: str) -> bool

class TmuxRuntime(BaseRuntime):
    def __init__(self, session_name: str)
```

## Edge Cases

- Сессия уже существует — подключиться к ней
- Окно не найдено — ValueError
- Пустой вывод capture_pane

## План реализации

### Step 1: Написать тест

```python
# tests/test_tmux_runtime.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from runtime.tmux_runtime import TmuxRuntime


@pytest.fixture
def mock_server():
    with patch("runtime.tmux_runtime.libtmux.Server") as mock:
        server = MagicMock()
        session = MagicMock()
        server.sessions.filter.return_value = []
        server.new_session.return_value = session
        mock.return_value = server
        yield server, session


def test_init_creates_session(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = []
    runtime = TmuxRuntime("ag-os")
    server.new_session.assert_called_once_with(session_name="ag-os", attach=False)


def test_create_agent(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    session.new_window.return_value = window
    runtime = TmuxRuntime("ag-os")
    result = runtime.create_agent("jira", 'claude -p "test"')
    session.new_window.assert_called_once_with(
        window_name="jira", attach=False
    )
    assert result == window.name


def test_destroy_agent(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    session.windows.filter.return_value = [window]
    runtime = TmuxRuntime("ag-os")
    runtime.destroy_agent("jira")
    window.kill.assert_called_once()


def test_send_prompt(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    pane = MagicMock()
    window.active_pane = pane
    session.windows.filter.return_value = [window]
    runtime = TmuxRuntime("ag-os")
    runtime.send_prompt("jira", "hello")
    pane.send_keys.assert_called_once_with("hello")


def test_read_output(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    pane = MagicMock()
    pane.capture_pane.return_value = ["line1", "line2"]
    window.active_pane = pane
    session.windows.filter.return_value = [window]
    runtime = TmuxRuntime("ag-os")
    output = runtime.read_output("jira")
    assert output == "line1\nline2"


def test_list_agents(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    w1 = MagicMock()
    w1.name = "master"
    w2 = MagicMock()
    w2.name = "jira"
    session.windows = [w1, w2]
    runtime = TmuxRuntime("ag-os")
    assert runtime.list_agents() == ["master", "jira"]
```

### Step 2: Запустить тест — FAIL

```bash
pytest tests/test_tmux_runtime.py -v
```

### Step 3: Создать base.py

```python
# runtime/base.py
from abc import ABC, abstractmethod


class BaseRuntime(ABC):
    @abstractmethod
    def create_agent(self, name: str, command: str = "") -> str:
        """Создать агента, вернуть идентификатор (window name или container id)."""

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
```

### Step 4: Реализовать tmux_runtime.py

```python
# runtime/tmux_runtime.py
import libtmux
from runtime.base import BaseRuntime


class TmuxRuntime(BaseRuntime):
    def __init__(self, session_name: str):
        self.session_name = session_name
        self._server = libtmux.Server()
        sessions = self._server.sessions.filter(session_name=session_name)
        if sessions:
            self._session = sessions[0]
        else:
            self._session = self._server.new_session(
                session_name=session_name, attach=False
            )

    def create_agent(self, name: str, command: str = "") -> str:
        window = self._session.new_window(window_name=name, attach=False)
        if command:
            window.active_pane.send_keys(command)
        return window.name

    def destroy_agent(self, name: str) -> None:
        windows = self._session.windows.filter(window_name=name)
        if windows:
            windows[0].kill()

    def send_prompt(self, name: str, prompt: str) -> None:
        windows = self._session.windows.filter(window_name=name)
        if not windows:
            raise ValueError(f"Agent '{name}' not found")
        windows[0].active_pane.send_keys(prompt)

    def read_output(self, name: str, lines: int = 50) -> str:
        windows = self._session.windows.filter(window_name=name)
        if not windows:
            raise ValueError(f"Agent '{name}' not found")
        captured = windows[0].active_pane.capture_pane()
        return "\n".join(captured)

    def list_agents(self) -> list[str]:
        return [w.name for w in self._session.windows]

    def agent_exists(self, name: str) -> bool:
        return bool(self._session.windows.filter(window_name=name))
```

### Step 5: Запустить тест — PASS

```bash
pytest tests/test_tmux_runtime.py -v
```

Expected: 6 passed

### Step 6: Commit

```bash
git add runtime/base.py runtime/tmux_runtime.py tests/test_tmux_runtime.py
git commit -m "feat: add BaseRuntime ABC and TmuxRuntime implementation"
```
