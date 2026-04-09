# AG-OS — Архитектура системы

**Версия:** 0.1.0
**Дата:** 2026-04-05

---

## 1. Обзор

AG-OS — мульти-агентный оркестратор для управления AI-агентами через Telegram и TUI-дашборд. Основной агент — Claude Code CLI (по подписке). Система поддерживает разные LLM-бэкенды (z.ai/Grok, OpenAI и др.), запуск агентов на хосте (tmux) и в Docker-контейнерах.

**Целевая платформа:** Ubuntu 22.04 VPS, работа 24/7.

### Ключевые принципы
- **Мастер на хосте** — Claude Code CLI как центр принятия решений
- **Тонкий транспорт** — Telegram-бот только маршрутизирует, не принимает решений
- **Гибридный runtime** — tmux для быстрых хостовых агентов, Docker для изоляции
- **Безопасность по умолчанию** — двухуровневая проверка промтов, подтверждения

---

## 2. Диаграмма компонентов

```
┌─────────────────────────────────────────────────────────────────┐
│                            AG-OS                                │
│                                                                  │
│    Интерфейсы                                                    │
│    ┌────────────────┐  ┌────────────────┐                       │
│    │  Telegram Bot   │  │  TUI Dashboard │                       │
│    │  (python-tg-bot)│  │  (Textual)     │                       │
│    └───────┬────────┘  └───────┬────────┘                       │
│            │                    │                                 │
│            └─────────┬──────────┘                                │
│                      ▼                                           │
│    Безопасность                                                  │
│    ┌────────────────────────────────┐                            │
│    │         Prompt Guard           │                            │
│    │  ┌──────────┐  ┌────────────┐ │                            │
│    │  │  Regex    │→ │ LLM Haiku  │ │                            │
│    │  │  Filter   │  │ Filter     │ │                            │
│    │  └──────────┘  └────────────┘ │                            │
│    └───────────────┬────────────────┘                            │
│                    ▼                                             │
│    Ядро                                                          │
│    ┌────────────────────────────────┐                            │
│    │        Agent Manager           │                            │
│    │  реестр · статусы · очереди    │                            │
│    └───────────────┬────────────────┘                            │
│                    │                                             │
│         ┌──────────┼──────────┐                                  │
│         ▼          ▼          ▼                                  │
│    ┌──────────┐ ┌──────────┐ ┌──────────┐                       │
│    │ Tmux     │ │ Docker   │ │Scheduler │                       │
│    │ Runtime  │ │ Runtime  │ │(APSched) │                       │
│    └──────────┘ └──────────┘ └──────────┘                       │
│                                                                  │
│    Данные                                                        │
│    ┌────────────────┐  ┌────────────────┐                       │
│    │  Memory System  │  │  SQLite DB     │                       │
│    │  (иерархическая)│  │  (единая)      │                       │
│    └────────────────┘  └────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘

Внешние процессы:

tmux session: "ag-os"              Docker containers
├── window: master (Claude CLI)    ├── ag-os-grok
├── window: jira   (Claude CLI)    ├── ag-os-review
├── window: code   (Claude CLI)    └── ag-os-* (динамические)
└── window: * (динамические)
```

---

## 3. Компоненты

### 3.1 Agent Manager

**Ответственность:** Центральный компонент. Управляет жизненным циклом агентов.

**Зависимости:** Database, TmuxRuntime, DockerRuntime, MemorySystem

**Интерфейс:**
```python
class AgentManager:
    async def create_agent(name, model, runtime, agent_type, config) -> dict
    async def destroy_agent(name) -> None
    async def send_prompt(name, prompt) -> None
    async def read_output(name, lines=50) -> str
    async def get_agent(name) -> dict | None
    async def list_agents() -> list[dict]
    async def update_status(name, status) -> None
```

**Логика выбора runtime:**
- `runtime == "host"` → TmuxRuntime (libtmux)
- `runtime == "docker"` → DockerRuntime (docker-py)
- Мастер-агент всегда `host`

### 3.2 Runtime Layer

Абстракция `BaseRuntime` с двумя реализациями:

```python
class BaseRuntime(ABC):
    def create_agent(name, command) -> str
    def destroy_agent(name) -> None
    def send_prompt(name, prompt) -> None
    def read_output(name, lines) -> str
    def list_agents() -> list[str]
    def agent_exists(name) -> bool
```

**TmuxRuntime:**
- Одна tmux-сессия `ag-os`
- Каждый агент = отдельное окно
- Отправка промтов через `send_keys`
- Чтение вывода через `capture_pane`

**DockerRuntime:**
- Контейнеры с префиксом `ag-os-`
- Ограничения ресурсов (CPU, RAM)
- Изолированные volumes
- Отправка промтов через `docker exec`

### 3.3 Telegram Bot

**Ответственность:** Транспортный слой. Парсинг сообщений, маршрутизация, UI.

**Поток сообщения:**
```
Telegram → Bot → Router (парсинг @тега)
                    ↓
              Prompt Guard (проверка)
                    ↓
              Agent Manager (отправка)
                    ↓
              Agent (tmux/docker)
                    ↓
              Agent Manager (чтение вывода)
                    ↓
              Bot → Telegram (ответ)
```

**Авторизация:** Whitelist Telegram user ID из config.yaml.

### 3.4 TUI Dashboard

**Ответственность:** Терминальный мониторинг и управление на сервере.

**Экраны:**
- **AgentsScreen** — таблица агентов с live-обновлением (2 сек)
- **ScheduleScreen** — таблица cron-задач

**Горячие клавиши:** N (new), K (kill), Enter (open), S (schedule), L (logs), Q (quit)

### 3.5 Prompt Guard

**Ответственность:** Проверка промтов перед отправкой агентам.

**Pipeline:**
```
Промт → Regex Filter (~1ms) → LLM Filter (~200ms) → Вердикт
```

**Вердикты:**
- `pass` — безопасный, пропустить
- `suspicious` — пропустить + уведомление
- `block` — заблокировать + алерт в Telegram

### 3.6 Memory System

**Ответственность:** Иерархическая память агентов.

**Модель доступа:**
```
Master (видит всё)
  ├── Global (видят все агенты)
  ├── Shared (видят указанные агенты)
  └── Private (видит только владелец)
```

**Интеграция:** При отправке промта Agent Manager загружает контекст памяти агента и добавляет как преамбулу.

### 3.7 Scheduler

**Ответственность:** Выполнение задач по расписанию.

**Логика:**
- Cron-выражение → APScheduler CronTrigger
- При срабатывании → проверка агента → send_prompt
- Динамические агенты поднимаются по требованию и гасятся после

---

## 4. Потоки данных

### 4.1 Telegram → Агент (прямое обращение)
```
User: "@jira отчёт за вчера"
  1. Bot получает сообщение
  2. Router парсит: agent=jira, prompt="отчёт за вчера"
  3. Bot проверяет авторизацию (whitelist)
  4. Prompt Guard проверяет промт (regex → LLM)
  5. Agent Manager загружает контекст памяти jira
  6. Agent Manager отправляет промт через TmuxRuntime
  7. Agent Manager обновляет статус: working
  8. (polling) Agent Manager читает вывод через capture_pane
  9. Bot отправляет ответ в Telegram
```

### 4.2 Telegram → Мастер → Агенты (делегирование)
```
User: "подними агента для ревью PR #42"
  1. Bot → нет тега → мастер-агент
  2. Мастер (Claude CLI) получает промт
  3. Мастер решает: создать динамического агента
  4. Мастер через tmux создаёт новое окно
  5. Мастер отправляет промт в новый агент
  6. По завершении мастер гасит агента
  7. Мастер присылает результат → Telegram
```

### 4.3 Scheduler → Агент
```
Cron trigger (0 9 * * 1-5)
  1. Scheduler срабатывает
  2. Проверяет существование целевого агента
  3. Если dynamic и не запущен → Agent Manager создаёт
  4. Agent Manager отправляет промт
  5. Результат логируется
  6. При ошибке → уведомление в Telegram
  7. Если dynamic → Agent Manager гасит после завершения
```

---

## 5. Модель данных (SQLite)

```sql
-- Реестр агентов
agents (id, name, model, runtime, type, status,
        current_task, tmux_window, container_id, config, created_at)

-- Иерархическая память
memory (id, owner, scope, shared_with, key, value,
        ttl, created_at, updated_at)

-- Расписание задач
schedule (id, cron_expression, agent_name, prompt,
          enabled, last_run, last_result, created_at)

-- Логи Prompt Guard
guard_logs (id, prompt, agent_name, regex_result,
            llm_result, final_result, created_at)
```

Единая SQLite БД для всех компонентов. Асинхронный доступ через aiosqlite.

---

## 6. Безопасность

| Слой | Механизм |
|------|----------|
| Авторизация | Whitelist Telegram user ID |
| Промты | Prompt Guard: regex + LLM Haiku |
| Действия | Inline-подтверждения для опасных операций |
| Изоляция | Docker без --privileged, ограниченные volumes |
| Ресурсы | Docker resource limits (CPU, RAM) |
| Секреты | Prompt Guard фильтрует доступ к env/токенам |
| Логирование | Все команды и ответы пишутся в SQLite |

---

## 7. Деплой

**Целевая среда:** Ubuntu 22.04 VPS

**Зависимости на хосте:**
- Python 3.11+
- tmux
- Docker Engine
- Node.js + npm (для Claude Code CLI)
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)

**Запуск:**
```bash
# Только Telegram-бот
python main.py bot --config config.yaml

# Только TUI
python main.py tui --config config.yaml

# Всё вместе
python main.py all --config config.yaml
```

**Процесс-менеджер:** systemd unit для автозапуска AG-OS.
