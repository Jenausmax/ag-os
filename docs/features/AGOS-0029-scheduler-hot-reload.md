---
id: AGOS-0029
title: Hot-reload schedule без рестарта бота
phase: 7 — Полировка
status: completed
depends_on: [AGOS-0027, AGOS-0028]
files_create: []
files_modify: [scheduler/scheduler.py, main.py, cli/commands.py, tests/test_scheduler.py, docs/quick-start.md]
---

## Описание

После AGOS-0028 у нас два независимых процесса, которые работают с таблицей `schedule`: живой бот (`python main.py bot`) и CLI (`python main.py schedule add ...`). Бот не увидит новую cron-запись, добавленную CLI, до следующего рестарта — потому что `AgScheduler` держит задачи в in-memory словаре APScheduler и не перечитывает БД.

Задача — сделать так, чтобы бот перечитывал таблицу `schedule` по внешнему сигналу без полного рестарта. Самый бюджетный и честный для Linux/Unix способ — `SIGUSR1`: бот ловит его и вызывает `scheduler.reload_from_db()`, который сверяет живые джобы с таблицей (diff: добавить новые, удалить отсутствующие, перерегистрировать изменённые). CLI-команда после успешного INSERT шлёт `SIGUSR1` процессу бота, если он найден.

На Windows сигналы работают иначе — fallback через файл-флаг (`.ag-os-reload` в рабочей директории), бот проверяет его раз в N секунд в отдельной корутине. На Linux/Docker — основной путь через SIGUSR1.

## Acceptance Criteria

- [ ] `AgScheduler.reload_from_db()` — идемпотентный метод: diff DB vs `self._jobs`, add/remove/update
- [ ] В `main.py` (Unix): регистрация `signal.signal(SIGUSR1, ...)` которая дёргает `scheduler.reload_from_db()` через `loop.call_soon_threadsafe`
- [ ] В `main.py` (Windows): опциональная корутина-watcher, проверяющая `.ag-os-reload` файл каждые N секунд (конфиг `scheduler.reload_poll_seconds`, дефолт 5)
- [ ] CLI `schedule add/rm` после успешного изменения БД пытается найти PID бота (через pid-файл или `docker compose exec`) и отправить сигнал / тач файла; при неуспехе — warning с инструкцией «перезапусти бот или подожди до следующего поллинга»
- [ ] Pid-файл бота: `main.py` пишет `ag-os.pid` в рабочую директорию на старте, удаляет в finally
- [ ] Тесты: `reload_from_db` при добавлении/удалении/изменении записей, идемпотентность
- [ ] Документация: раздел «Hot-reload расписания» в quick-start
- [ ] Все тесты проходят

## Затрагиваемые модули

- `scheduler/scheduler.py` — метод `reload_from_db()`, diff-логика
- `main.py` — pid-файл, signal handler (Unix) / file-watcher (Windows)
- `cli/commands.py` — `_notify_bot()` helper после schedule-операций
- `tests/test_scheduler.py` — тесты reload-логики
- `docs/quick-start.md` — секция про hot-reload

## Ключевые интерфейсы

```python
class AgScheduler:
    async def reload_from_db(self) -> ReloadReport:
        """Синхронизировать живые джобы с таблицей schedule.

        Возвращает отчёт: added/removed/updated id-шники.
        Идемпотентно — можно звать сколько угодно раз.
        """
        db_tasks = {t["id"]: t for t in await self.list_tasks() if t["enabled"]}
        live_ids = set(self._jobs.keys())
        db_ids = set(db_tasks.keys())
        added = db_ids - live_ids
        removed = live_ids - db_ids
        possibly_updated = db_ids & live_ids
        # add new
        for tid in added:
            self._register_job(db_tasks[tid])
        # remove stale
        for tid in removed:
            self._scheduler.remove_job(self._jobs[tid])
            del self._jobs[tid]
        # update: сравниваем cron/agent/prompt, если изменилось — re-register
        for tid in possibly_updated:
            if self._job_differs(tid, db_tasks[tid]):
                self._scheduler.remove_job(self._jobs[tid])
                self._register_job(db_tasks[tid])
        return ReloadReport(added=added, removed=removed, updated=...)
```

```python
# main.py — signal handler (Unix)
def _install_reload_handler(loop, scheduler):
    if hasattr(signal, "SIGUSR1"):
        def _handler(_sig, _frame):
            asyncio.run_coroutine_threadsafe(scheduler.reload_from_db(), loop)
        signal.signal(signal.SIGUSR1, _handler)
```

## Edge Cases

- Сигнал прилетает во время работающего job — `remove_job` для этого же id. APScheduler штатно обрабатывает: либо дожидается, либо отменяет. Проверить поведение в интеграционном тесте.
- CLI на Windows в docker-compose → fallback через файл-флаг обязателен
- Гонка: два CLI-вызова подряд, бот обрабатывает один сигнал → второй reload увидит обе записи, всё ок (идемпотентность)
- PID-файл мёртвый (бот упал, не убрал) → CLI при отправке сигнала увидит `ProcessLookupError`, логирует warning, не падает
- Пользователь руками правит SQL → тот же сигнал `SIGUSR1` работает, бот перечитает

## План реализации

### Step 1: reload_from_db

Реализовать метод в `AgScheduler` с тестами. Проверить все 4 перехода (add, remove, no-op, update).

### Step 2: pid-файл и signal handler

`main.py` при старте `run_bot` / `run_all` — пишет pid, при выходе — удаляет. Регистрирует SIGUSR1 handler на Unix.

### Step 3: Windows fallback

Опциональная корутина-watcher, читающая `.ag-os-reload`. Конфигурируется `scheduler.reload_poll_seconds`.

### Step 4: CLI notify

В `cli/commands.py` после `schedule_add`/`rm`/`toggle` — вызывать `_notify_bot()`: читает pid-файл, шлёт SIGUSR1 (Unix) или `touch .ag-os-reload` (Windows). При ошибке — warning, не падение.

### Step 5: Тесты

- Unit: `reload_from_db` для всех сценариев
- Интеграционный: in-memory SQLite + mock APScheduler, проверка что `_jobs` словарь синхронизирован с БД после сигнала

### Step 6: Документация

Секция «Hot-reload» в quick-start: как работает, что на Unix и Windows по-разному, как проверить что бот услышал сигнал (лог).

### Step 7: Commit

```bash
git add scheduler/ main.py cli/commands.py tests/test_scheduler.py docs/quick-start.md
git commit -m "feat(AGOS-0029): hot-reload schedule from DB on SIGUSR1 / file trigger"
```
