# AG-OS

Мульти-агентный оркестратор для управления AI-агентами через Telegram и TUI-дашборд. Основной агент — Claude Code CLI. Целевая платформа — Ubuntu 22.04, работа 24/7.

## Возможности

- **Telegram-бот** с маршрутизацией по `@тегу` агента и двухуровневым Prompt Guard (regex + LLM Haiku)
- **TUI-дашборд** (Textual) с таблицей агентов и расписанием
- **Tmux и Docker рантаймы** — мастер всегда на хосте, агенты — в изолированных контейнерах или окнах tmux
- **Иерархическая память** с scope (private/shared/global) и правилами доступа
- **Планировщик** на APScheduler для cron-задач
- **SQLite** через aiosqlite как единая БД

## 📖 Подробное руководство

Полный разбор установки, конфигов и всех юзкейсов (включая мульти-модельные провайдеры —
подписка Claude, Anthropic API, z.ai, MiniMax, локальная Ollama) лежит в
**[docs/quick-start.md](docs/quick-start.md)**. Там пошагово расписано, что и в какой файл
писать под каждый сценарий.

Справка по CLI-подкомандам (`python main.py agent|schedule|memory|vault ...`) —
в **[docs/cli-reference.md](docs/cli-reference.md)**.

Мастер-агент подгружает три скилла из `.claude/skills/agos-*` для управления
агентами, планировщиком и Obsidian vault. Готовые промты-шаблоны для типовых
запросов к мастеру — в **[docs/prompts/master-prompts.md](docs/prompts/master-prompts.md)**.

## Быстрый старт

### Linux / macOS / WSL2

```bash
bash scripts/setup.sh
```

Скрипт спросит режим установки:

- **native** — ставит `tmux` и Python 3.11 (через apt или brew), создаёт venv, ставит зависимости. Запуск на текущей машине.
- **docker** — собирает два образа (`ag-os-full:latest` для sub-агентов и `ag-os:latest` для самого приложения), поднимает через `docker compose`. Контейнер общается с хостовым Docker через socket mount, sub-агенты создаются как sibling-контейнеры.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Скрипт детектит WSL2 и Docker Desktop, предлагает один из вариантов:

1. **WSL2** — передаёт управление `setup.sh` внутри WSL (рекомендуемый путь для разработки)
2. **Docker Desktop** — сборка образов на Windows напрямую. Потребуется подправить пути `/data/ag-os/*` в `docker-compose.yml` под Windows-хост или использовать WSL2.

## Конфигурация

Отредактируй `config.yaml` перед запуском:

```yaml
telegram:
  token: "..."              # токен от @BotFather
  allowed_users: [123456]   # whitelist Telegram user ID

guard:
  enabled: true
  llm_enabled: true
  haiku_api_key: "..."      # Anthropic API key для LLM-фильтра
```

Полный список параметров — в `config.yaml`.

## Запуск

### Native

```bash
source .venv/bin/activate
python main.py bot   --config config.yaml   # только Telegram-бот
python main.py tui   --config config.yaml   # только TUI
python main.py all   --config config.yaml   # бот + TUI параллельно
```

### Docker

Первый логин Claude Code CLI (один раз, интерактивно — volume `claude-config` сохранит сессию):

```bash
docker compose run --rm ag-os claude login
```

Запуск:

```bash
docker compose up -d ag-os                              # бот в фоне
docker compose run --rm ag-os python main.py tui ...    # TUI
docker compose logs -f ag-os                            # логи
```

## Архитектура

```
Интерфейсы (Telegram Bot, TUI Dashboard)
    → Prompt Guard (regex → LLM Haiku)
        → Agent Manager
            → Runtime Layer (TmuxRuntime | DockerRuntime)
            → Memory System
            → Scheduler
    → SQLite
```

Подробнее — в `CLAUDE.md` и `docs/`.

## Docker sibling-контейнеры

В docker-режиме AG-OS монтирует `/var/run/docker.sock` и общается с хостовым демоном. Sub-агенты создаются как **sibling-контейнеры** — рядом с AG-OS, а не внутри него.

Критично: пути к workspace-ам должны совпадать внутри и снаружи контейнера, поэтому `/data/ag-os/workspaces` монтируется в тот же `/data/ag-os/workspaces` внутри. Иначе sub-агенты получат битые volume-пути.

## Два Dockerfile

- `Dockerfile.agent` — образ для sub-агентов под `DockerRuntime` (Ubuntu + Claude Code CLI), тег `ag-os-full:latest`
- `Dockerfile.app` — образ для самого AG-OS (Python 3.11 slim + tmux + Claude Code CLI + зависимости), тег `ag-os:latest`

`setup.sh` и `setup.ps1` собирают оба.

## Тесты

```bash
pytest tests/ -v --cov=.
```

## Лицензия

См. `LICENSE`.
