# AG-OS CLI Reference

`python main.py` — точка входа AG-OS. Помимо запуска в runtime-режимах (`bot`, `tui`, `all`), поддерживает подкоманды управления агентами, расписанием и памятью. Все они читают/пишут в ту же SQLite-БД, что и живой бот, и дают стабильный control-plane — в том числе для самого мастер-агента, которому достаточно выполнить `python main.py agent create ...` через bash-tool.

## Общие флаги

```
python main.py [--config config.yaml] <command> <subcommand> [options]
```

- `--config` — путь к `config.yaml`. Дефолт `config.yaml` в cwd. Применяется ко всем подкомандам.
- Все list-команды принимают `--json` для машиночитаемого вывода.

## Runtime-режимы

| Команда | Что делает |
|---|---|
| `python main.py bot` | Поднимает Telegram-бот, планировщик и Prompt Guard |
| `python main.py tui` | Textual-дашборд (без шедулера) |
| `python main.py all` | Бот + TUI параллельно |
| `python main.py` *(без аргументов)* | Алиас на `bot` — для обратной совместимости |

## `agent` — управление агентами

### `agent create`

Создаёт агента и запускает его в указанном runtime.

```
python main.py agent create \
    --name mail-bot \
    --runtime docker \
    --model claude-cli \
    --provider zai-glm \
    --type permanent \
    [--json]
```

| Флаг | Обязательный | Описание |
|---|---|---|
| `--name` | да | Уникальное имя агента |
| `--runtime` | нет (host) | `host` (tmux) или `docker` |
| `--model` | нет (claude-cli) | Человекочитаемый лейбл модели |
| `--provider` | нет | Ключ из `config.model_providers` — z.ai, Anthropic API, и т.д. |
| `--type` | нет (dynamic) | `permanent` или `dynamic` |
| `--json` | — | Вернуть созданного агента JSON-ом |

Ошибки (fail-fast, exit-code 1):
- Agent с таким именем уже существует
- Провайдер не найден в `config.model_providers`
- Для провайдера задан `api_key_env`, но переменная не выставлена в shell

### `agent destroy`

```
python main.py agent destroy --name mail-bot
```

Останавливает runtime (tmux-окно или docker-контейнер) и удаляет запись из БД.

### `agent list`

```
python main.py agent list [--json]
```

Текстовый вывод: `name runtime status model`. JSON: массив объектов с полной строкой из таблицы `agents`.

## `schedule` — cron-задачи

### `schedule add`

```
python main.py schedule add \
    --cron "0 * * * *" \
    --agent master \
    --prompt "проверь новую почту за последний час" \
    [--json]
```

| Флаг | Описание |
|---|---|
| `--cron` | 5-полей cron-выражение в кавычках. Валидация через `CronTrigger.from_crontab` до записи в БД |
| `--agent` | Имя существующего агента |
| `--prompt` | Текст промта |

**Важно:** живой бот не перечитывает таблицу `schedule` — новая запись, добавленная через CLI, подхватится только на рестарте бота. Это лечится в AGOS-0029 через `SIGUSR1`. Пока что — рестарт, или используй Telegram-команду `/schedule_add`, которая идёт через живой `AgScheduler.add_task`.

### `schedule list`

```
python main.py schedule list [--json]
```

Текст: `#id [ON|OFF] cron @agent → prompt`.

### `schedule rm`

```
python main.py schedule rm --id 7
```

### `schedule run`

```
python main.py schedule run --id 7
```

Немедленно отправляет промт задачи агенту (для отладки без ожидания cron). Требует живого runtime у агента (tmux-окно/контейнер должны существовать).

## `memory` — иерархическая память

### `memory remember`

```
python main.py memory remember \
    --agent master \
    --key rule \
    --value "no force push to main" \
    --scope global \
    [--ttl "2026-12-31 23:59:59"] \
    [--json]
```

| Флаг | Описание |
|---|---|
| `--agent` | Владелец записи (может быть любой, не только существующий агент) |
| `--key` | Ключ записи |
| `--value` | Значение |
| `--scope` | `private` / `shared` / `global`. Default `private` |
| `--ttl` | ISO-дата истечения. Default — без TTL |

### `memory get`

```
python main.py memory get --agent master [--key rule] [--json]
```

Если `--key` задан — возвращает одну запись (или fail, если нет доступа). Без `--key` — весь контекст, видимый указанному агенту (private свои + shared где он в списке + global).

### `memory forget`

```
python main.py memory forget --id 42
```

Удаляет запись по id.

## Коды возврата

- `0` — успех
- `1` — ошибка (агент не найден, невалидный cron, отсутствующая env-переменная, нарушение уникальности, и т.п.)

## Примеры автоматизации

### Создать нового sub-агента «из мастера»

Мастер в своём tmux-окне делает:

```bash
python main.py agent create --name researcher --runtime docker --provider anthropic-api
python main.py memory remember --agent researcher --key role --value "ресёрч по ИБ" --scope private
python main.py schedule add --cron "0 9 * * 1-5" --agent researcher --prompt "сводка новостей ИБ за вчера"
```

Три команды — агент создан, ему записан контекст в память, и он поставлен на cron. Дальше после рестарта бота (или hot-reload в AGOS-0029) задача начнёт исполняться.

### Bulk-запрос через JSON

```bash
python main.py agent list --json | jq -r '.[] | select(.runtime == "docker") | .name'
```

Вернёт имена всех docker-агентов — удобно для скриптов.
