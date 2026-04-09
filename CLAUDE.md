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

## Команды

```bash
# Запуск Telegram-бота
python main.py bot --config config.yaml

# Запуск TUI-дашборда
python main.py tui --config config.yaml

# Запуск всего вместе
python main.py all --config config.yaml

# Установка зависимостей
pip install -r requirements.txt

# Запуск тестов
pytest tests/

# Запуск одного теста
pytest tests/test_agent_manager.py -v
```

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
