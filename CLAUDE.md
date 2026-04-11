# CLAUDE.md

Этот файл содержит инструкции для Claude Code (claude.ai/code) при работе с кодом в этом репозитории.

## О проекте

AG-OS — мульти-агентный оркестратор для управления AI-агентами через Telegram и TUI-дашборд. Основной агент — Claude Code CLI (по подписке). Целевая платформа — Ubuntu 22.04 VPS, работа 24/7.

## Стек технологий

- **Язык:** Python 3.11+
- **Telegram:** python-telegram-bot v21+
- **TUI:** Textual
- **tmux API:** libtmux
- **Docker:** docker-py
- **Планировщик:** APScheduler 3.x (AsyncIOScheduler)
- **БД:** SQLite через aiosqlite (единая БД для всех компонентов)
- **LLM-фильтр:** Claude Haiku API
- **Конфигурация:** YAML (config.yaml)

## Установка

Пользователь ставит проект через интерактивные скрипты:

- `scripts/setup.sh` — Linux / macOS / WSL2. Меню: `native` (tmux + venv на хосте) или `docker` (всё в контейнере).
- `scripts/setup.ps1` — Windows. Детектит WSL2 и Docker Desktop, маршрутизирует.

Подробности — в `README.md`.

## Команды

```bash
# Установка (интерактивный скрипт)
bash scripts/setup.sh               # Linux/macOS/WSL
powershell scripts/setup.ps1        # Windows

# Запуск (native)
python main.py bot --config config.yaml   # только Telegram-бот
python main.py tui --config config.yaml   # только TUI
python main.py all --config config.yaml   # бот + TUI параллельно

# Запуск (docker)
docker compose run --rm ag-os claude login   # первый логин Claude Code CLI
docker compose up -d ag-os                    # бот в фоне
docker compose logs -f ag-os                  # логи

# Тесты
pytest tests/
pytest tests/test_agent_manager.py -v
```

## Docker-сборка

Проект использует **два** Dockerfile:

- `Dockerfile.agent` → тег `ag-os-full:latest` — образ для sub-агентов, которые запускает `DockerRuntime`. Ubuntu + Claude Code CLI.
- `Dockerfile.app` → тег `ag-os:latest` — образ для самого AG-OS (бот + TUI). Python 3.11-slim + tmux + Claude Code CLI + зависимости.

В docker-режиме AG-OS монтирует `/var/run/docker.sock` хоста и создаёт sub-агентов как **sibling-контейнеры** (не через DinD). Критично: пути к workspace-ам (`/data/ag-os/workspaces`) монтируются **идентично** внутри и снаружи, иначе sibling-контейнеры получат битые volume-пути.

Логин Claude Code CLI хранится в named volume `claude-config` (`/root/.claude` внутри контейнера) и переживает рестарты.

## Архитектура

Система состоит из 7 основных компонентов, связанных через Agent Manager:

```
Интерфейсы (Telegram Bot, TUI Dashboard)
    → Prompt Guard (regex → LLM Haiku) — двухуровневая проверка промтов
        → Agent Manager — центральный компонент, CRUD агентов
            → Runtime Layer (TmuxRuntime | DockerRuntime) — запуск и общение с агентами
            → Memory System — иерархическая память (private/shared/global)
            → Scheduler (APScheduler) — cron-задачи
    → SQLite — единая БД для всех данных
```

### Ключевые решения

- **Мастер-агент** всегда на хосте (tmux), остальные — tmux или Docker
- **Telegram Bot** — тонкий транспорт, не принимает решений. Маршрутизация через `@тег`
- **Prompt Guard** — regex (~1ms) отсекает очевидное, LLM Haiku (~200ms) ловит сложные атаки. При ошибке LLM — промт = SUSPICIOUS (fail-safe)
- **Memory** — мастер видит всё, агенты видят своё + shared + global. Контекст памяти добавляется как преамбула при отправке промта
- **Tmux** — сессия `ag-os`, каждый агент = окно. Общение через `send_keys` / `capture_pane`
- **Docker** — контейнеры `ag-os-{name}`, без `--privileged`, ограниченные volumes и ресурсы

### Структура модулей

- `core/` — Agent Manager, модели данных, конфигурация
- `runtime/` — BaseRuntime (ABC) с TmuxRuntime и DockerRuntime
- `telegram/` — бот, роутер (@тегов), обработчики команд, inline-подтверждения
- `tui/` — Textual-приложение (AgentsScreen, ScheduleScreen)
- `scheduler/` — APScheduler обёртка
- `memory/` — CRUD памяти + правила доступа по scope
- `guard/` — Prompt Guard (оркестрация, regex_filter, llm_filter, rules.yaml)
- `db/` — aiosqlite подключение, schema.sql

## Модель данных (SQLite)

4 таблицы: `agents` (реестр), `memory` (иерархическая память с scope/TTL), `schedule` (cron-задачи), `guard_logs` (логи проверок промтов).

## Фазы реализации

1. MVP: Agent Manager + tmux runtime + Telegram Bot
2. Безопасность: Prompt Guard + подтверждения
3. TUI Dashboard
4. Memory System
5. Scheduler + cron
6. Docker Runtime
7. Полировка: логирование, мониторинг, обработка ошибок

## Соглашения

- Весь async-код через asyncio
- Авторизация Telegram — whitelist user ID из config.yaml
- Git flow: фичи от `develop`, ветки `feature/[KEY-N]-описание`
- Документация и комментарии на русском языке
