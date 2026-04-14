---
id: AGOS-0028
title: CLI control plane для self-automation мастера
phase: 7 — Полировка
status: completed
depends_on: [AGOS-0027]
files_create: [cli/__init__.py, cli/commands.py, tests/test_cli.py, docs/cli-reference.md]
files_modify: [main.py, docs/quick-start.md]
---

## Описание

Дать мастер-агенту (и пользователю) стабильный control-plane для управления AG-OS без правки кода и без прямых INSERT в SQLite. Мастер живёт в tmux на хосте, значит умеет запускать bash-команды — то есть `python main.py agent create ...` для него это обычный tool-call через bash. Это закрывает запрос «мастер сам создаёт агентов и расписания по промту пользователя» (см. обсуждение AGOS-0026/0027) без рискованной self-modifying логики.

Задача — расширить `main.py` подкомандами `agent`, `schedule`, `memory`, которые ходят в ту же БД, что и живой бот. Синхронизация с работающим ботом — через триггер из AGOS-0029 (шедулер перечитывает `schedule` по сигналу).

## Acceptance Criteria

- [ ] `python main.py agent create --name X --runtime docker --provider zai-glm [--model Y]` — создаёт агента, пишет в БД, при docker-runtime запускает контейнер с env от провайдера
- [ ] `python main.py agent destroy --name X` — зовёт `AgentManager.destroy_agent`
- [ ] `python main.py agent list [--json]` — список агентов
- [ ] `python main.py schedule add --cron "0 * * * *" --agent X --prompt "..."` — insert в таблицу + (если AGOS-0029 замержен) триггер живого бота
- [ ] `python main.py schedule list [--json]` / `schedule rm --id N` / `schedule run --id N`
- [ ] `python main.py memory remember --agent X --key K --value V --scope private|shared|global`
- [ ] `python main.py memory get --agent X [--key K]`
- [ ] Все подкоманды используют общий `config.yaml` (флаг `--config`), поднимают `Database`/`AgentManager` через общий bootstrap-хелпер
- [ ] Fail-fast ошибки с понятным stderr (агент не найден, провайдер не задан, cron невалидный)
- [ ] JSON-вывод (`--json`) для всех list-команд — нужен мастеру для машинного парсинга
- [ ] Тесты: end-to-end на SQLite in-memory, без tmux/docker (мокаем runtime)
- [ ] `docs/cli-reference.md` — полная справочная дока с примерами
- [ ] Секция в `docs/quick-start.md` «Мастер управляет AG-OS» с юзкейсом промта «создай агента для почты, который раз в час сам её проверяет»

## Затрагиваемые модули

- `main.py` — перевод argparse на подкоманды. Существующие `bot`/`tui`/`all` сохранить как есть (back-compat).
- `cli/commands.py` — новый модуль с реализацией каждой подкоманды. Не дублирует логику AgentManager/Scheduler — зовёт их методы.
- `cli/__init__.py` — пустой.
- `tests/test_cli.py` — через `subprocess`-free вызов `cli.commands.main(["agent", "list"])` или прямой dispatch.
- `docs/cli-reference.md` — новый файл.
- `docs/quick-start.md` — юзкейс самоавтоматизации.

## Ключевые интерфейсы

```python
# main.py — подкоманды поверх существующего парсера
parser = argparse.ArgumentParser(...)
sub = parser.add_subparsers(dest="mode", required=False)

# back-compat: mode=bot/tui/all без sub
# новое: mode=agent|schedule|memory с вложенными субпарсерами
agent_sp = sub.add_parser("agent")
agent_cmd = agent_sp.add_subparsers(dest="cmd")
agent_cmd.add_parser("create").add_argument(...)
...
```

```python
# cli/commands.py
async def agent_create(args, ctx: CliContext): ...
async def agent_destroy(args, ctx): ...
async def agent_list(args, ctx): ...
async def schedule_add(args, ctx): ...
# ...
```

`CliContext` содержит уже поднятые `Database`, `AgentManager`, `AgScheduler` (без `.start()` — CLI-команды не запускают живой таймер).

## Edge Cases

- CLI запускается пока бот живой — обе инстанции пишут в ту же БД. Для create/destroy docker-агента гонки минимальны (контейнер уникален по имени). Для schedule — бот не увидит новую запись до сигнала (AGOS-0029) или рестарта.
- `agent create` с host-runtime из CLI создаёт tmux-окно. Если бот уже владеет той же сессией — libtmux увидит живую сессию, всё ок. Проверить на интеграционном тесте.
- Создание агента с провайдером, у которого нет env-переменной — fail-fast с сообщением.
- `memory remember` без agent — отклонить.
- `schedule add` с невалидным cron — парсить через `CronTrigger.from_crontab` до записи в БД.

## План реализации

### Step 1: Рефакторинг argparse

Оставить существующие `bot`/`tui`/`all` как алиасы верхнего уровня. Добавить subparsers для `agent`/`schedule`/`memory`. Общий флаг `--config`.

### Step 2: CliContext + bootstrap-хелпер

Выделить из текущего `bootstrap()` функцию `init_core(config_path)` → возвращает `(db, manager, config)` без стартованного шедулера и без валидации провайдеров запущенных агентов (это нужно только для bot/all). CLI зовёт её.

### Step 3: cli/commands.py

Реализация всех подкоманд. Для list-команд — поддержка `--json` через `json.dumps`.

### Step 4: Тесты

`tests/test_cli.py`: для каждой команды — прямой вызов её async-функции с мок-runtime. Проверка stdout через `capsys`.

### Step 5: Документация

`docs/cli-reference.md` — табличка со всеми командами, флагами, примерами вывода.

Секция в `docs/quick-start.md`: «Мастер управляет AG-OS» — объясняется, как в промте мастеру сказать «создай агента Х и поставь его на cron», показать, какие bash-команды мастер под это будет запускать. Важно: подчеркнуть, что это **не** самомодификация кода, а вызов стабильного API.

### Step 6: Commit

```bash
git add cli/ main.py tests/test_cli.py docs/cli-reference.md docs/quick-start.md
git commit -m "feat(AGOS-0028): CLI control plane for agent/schedule/memory management"
```
