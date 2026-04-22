# AGOS-0041: Очистка контекста агентов перед cron-задачами

**Дата:** 2026-04-22
**Статус:** утверждено, ожидает реализации
**Ветка:** `feature/AGOS-0041-clear-context-before-cron`

## Проблема

Контекстные окна подопечных агентов разрастаются от периодических задач: REPL Claude CLI хранит всю историю запусков. Пример из жизни: агент `finik` (финансовые отчёты) за ~2 дня (~50 часов работы по cron) накопил окно, существенно ужравшее подписку.

## Цель

Перед каждым cron-тиком (по умолчанию) runtime чистит REPL подопечного агента. Чтобы агент не «забыл» предысторию совсем, prompt задачи содержит триггер скилла `agos-agent-recall`, который заставляет агента восстановить контекст из vault-заметок перед выполнением.

## Не-цели

- Не трогаем механизм ресуррекции агентов (AGOS-0037).
- Не меняем поведение разовых (one-shot) задач — для них чистка бессмысленна.
- Не реализуем порог по размеру контекста / по числу запусков (вариант B из брейншторма отклонён в пользу D).
- Мастер-агент не вовлекается в каждый cron-тик (вариант B отклонён в пользу A).

## Архитектура

```
APScheduler tick
    ↓
Scheduler handler читает task из БД (включая флаг clear_before)
    ↓
если clear_before: await runtime.clear_context(agent_name)
    ↓
await runtime.send_prompt(agent_name, prompt)
    ↓
агент выполняет prompt; при наличии триггера запускает скилл agos-agent-recall;
скилл читает vault/agents/<name>/, восстанавливает состояние, агент выполняет задачу.
```

Мастер-агент вовлечён только в момент **создания** периодической задачи: его скилл `agos-schedule-management` оборачивает prompt в шаблон с триггером recall и выставляет `clear_before=true`.

## Компоненты

### 1. Схема БД

В таблицу `schedule` добавить колонку:

```sql
ALTER TABLE schedule ADD COLUMN clear_before INTEGER NOT NULL DEFAULT 1;
```

Миграция: для существующих задач значение по умолчанию `1`. Хранится вместе с cron-выражением и prompt-ом.

Соответствующий dataclass `ScheduleTask` (в `core/models.py` или `scheduler/`) получает поле `clear_before: bool = True`.

### 2. Runtime API

В `runtime/base.py` — новый абстрактный метод:

```python
@abstractmethod
async def clear_context(self, agent_name: str) -> None:
    """Сбросить REPL-контекст агента. No-op, если runtime stateless."""
```

**TmuxRuntime.clear_context** (`runtime/tmux_runtime.py`):
- Шлёт строку `/clear` + Enter в pane агента через `send_keys`.
- Короткая пауза `await asyncio.sleep(0.3)`, чтобы Claude CLI успел обработать команду до следующего prompt-а.
- Если окно/сессия отсутствует — поднимает исключение (как и существующие методы; обработка — выше по стеку).

**DockerRuntime.clear_context** (`runtime/docker_runtime.py`):
- No-op. Docker-runtime использует batch-режим (`claude -p` на каждый prompt через `exec_run`), контекст между вызовами не сохраняется. Метод просто `return`.

### 3. Scheduler

В `scheduler/scheduler.py` — обработчик сработавшей задачи:

```python
async def _run_task(task: ScheduleTask) -> None:
    if task.clear_before:
        try:
            await self._runtime.clear_context(task.agent_name)
        except Exception as exc:
            logger.warning("clear_context failed for %s: %s; skipping tick", task.agent_name, exc)
            return
    await self._runtime.send_prompt(task.agent_name, task.prompt)
```

Точные имена методов сверить с текущим API при реализации (`send_prompt` / `send_keys` / etc).

### 4. Скилл `agos-agent-recall`

Новый скилл в `.claude/skills/agos-agent-recall/SKILL.md`. Описание (для frontmatter — триггерится по упоминанию или фразам «вспомни контекст», «recall», «перед задачей вспомни»).

Процедура:
1. Прочитать `vault/agents/<AG_OS_AGENT_NAME>/` — последние ~10 raw-заметок (по mtime).
2. Найти записи, релевантные текущей задаче (по ключевым словам из prompt-а).
3. Сформулировать кратко (для себя): что делал в прошлые запуски, на чём остановился, какие были выводы.
4. Только после этого — приступать к выполнению задачи.

Точное число заметок и эвристика релевантности — на усмотрение скилла; не закрепляем в коде.

### 5. Мастерский скилл `agos-schedule-management`

Обновить существующий скилл. При создании **периодической** (cron) задачи:

- по умолчанию `clear_before=true`;
- prompt оборачивается в шаблон:
  ```
  Используй скилл agos-agent-recall, чтобы вспомнить контекст из своих заметок в vault.

  Задача: <оригинальный prompt>
  ```

Для one-shot задач — `clear_before=false`, шаблон не применяется.

### 6. CLI

`cli/commands.py` — у `schedule add` (или эквивалентной команды) добавить флаг:

- `--no-clear` — выставить `clear_before=false` для периодической задачи (для редких сценариев, где контекст между тиками полезен и подписка не критична).

По умолчанию для cron-задач — `clear_before=true`.

## Обработка ошибок

- `clear_context` бросает (pane мёртв, агент не поднят) → scheduler логирует warning, **пропускает тик** без падения. Следующий тик попробует снова. Ресуррекция — отдельный механизм.
- Скилл `agos-agent-recall` отсутствует у агента → агент проигнорирует триггер и выполнит задачу как раньше. Безопасная деградация, ломать ничего не должно.
- Vault недоступен / папка агента пуста → скилл должен явно констатировать это в своей внутренней «сводке» и продолжить выполнение задачи без recall.

## Тесты

В `tests/`:

- `test_schedule_clear_before_defaults_true` — после миграции у новых задач поле = 1.
- `test_tmux_runtime_clear_context_sends_slash_clear` — `send_keys` получает строку, начинающуюся с `/clear`, и Enter.
- `test_docker_runtime_clear_context_is_noop` — метод существует, ничего не зовёт у docker-клиента.
- `test_scheduler_calls_clear_before_prompt` — порядок: сначала `clear_context`, потом `send_prompt`.
- `test_scheduler_skips_clear_when_flag_false` — при `clear_before=false` runtime.clear_context не зовётся.
- `test_scheduler_skips_tick_when_clear_fails` — исключение из clear не роняет scheduler, tick пропущен, ошибка в логе.
- Обновить существующие schedule-тесты на новое поле БД и dataclass.

## Миграция

В проекте нет отдельного инструмента миграций — схема создаётся через `CREATE TABLE IF NOT EXISTS` в `db/schema.sql` при старте. Для совместимости со старыми БД:

1. В `db/schema.sql` колонка `clear_before INTEGER NOT NULL DEFAULT 1` появляется в `CREATE TABLE schedule (...)` — для свежих установок.
2. В `db/database.py` (или там, где исполняется `schema.sql` при старте) — после применения схемы выполнить идемпотентный апгрейд: `PRAGMA table_info(schedule)`, и если колонки `clear_before` нет — `ALTER TABLE schedule ADD COLUMN clear_before INTEGER NOT NULL DEFAULT 1`.

Существующие задачи получают `clear_before=1` (дефолт). Это меняет их поведение: они начнут чиститься перед каждым тиком. Считаем приемлемым — это и есть цель фичи. Если у пользователя есть конкретная задача, где это не нужно, пересоздаст с `--no-clear`.

## Открытые вопросы

Нет. Все варианты разобраны на брейншторме (D + B + A для clear-policy / preamble-source / initiator).
