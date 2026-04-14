---
name: agos-agent-management
description: >
  Управление sub-агентами AG-OS через CLI control-plane. Используй этот скилл,
  когда пользователь просит создать, удалить или посмотреть агентов, сменить
  им провайдера/модель, или говорит "создай агента X", "подними контейнер для Y",
  "какие агенты у меня сейчас работают", "убей агента Z", "перезапусти агента".
  Триггерится на любые запросы связанные с жизненным циклом sub-агентов.
---

# AG-OS: управление агентами

Этот скилл даёт мастер-агенту стабильный control-plane для создания и управления sub-агентами через AG-OS CLI без прямых правок кода или SQL.

## Ключевой принцип

Ты **не редактируешь** код AG-OS (`core/`, `runtime/`, `scheduler/`). Для всех операций с агентами используй подкоманды `python main.py agent ...`. Это безопасный API с валидацией и fail-fast ошибками.

## Перед началом — контекст

Прежде чем что-то делать, выясни:
- **Где запускается агент?** `host` (tmux на хосте) или `docker` (контейнер). Хост — для master и для вещей, которые должны видеть файловую систему проекта. Docker — для изолированных задач.
- **На какой модели?** Посмотри доступные провайдеры в `config.yaml` → секция `model_providers`. Если пользователь не уточнил — дефолт `claude-subscription` (подписка) для мастера и `zai-glm` или `anthropic-api` для sub-агентов.
- **Тип агента.** `permanent` — живёт между рестартами AG-OS. `dynamic` — создаётся под разовую задачу и удаляется.

## Команды

### Посмотреть всех агентов

```bash
python main.py agent list
# или машиночитаемо:
python main.py agent list --json
```

Выдаёт `name runtime status model`. Используй перед созданием нового — чтобы не получить коллизию имени.

### Создать агента

```bash
python main.py agent create \
    --name <name> \
    --runtime <host|docker> \
    --model <human-readable-label> \
    --provider <provider-key-from-config> \
    --type <permanent|dynamic>
```

**Обязательные решения:**
- `--name` — уникален по всей БД. Формат: lowercase, без пробелов, желательно короткий (`mail-bot`, `researcher`, `coder-glm`).
- `--runtime` — `docker` по умолчанию для новых sub-агентов.
- `--provider` — ключ из `config.model_providers`. Если не знаешь какие есть — сначала `grep -A3 model_providers config.yaml`.

**Валидация:** CLI упадёт с понятной ошибкой если:
- агент с таким именем существует → сначала `agent destroy` или выбери другое имя;
- провайдер не найден → пользователю надо добавить в `config.yaml`;
- env-переменная провайдера не выставлена → попросить пользователя экспортировать её.

### Удалить агента

```bash
python main.py agent destroy --name <name>
```

Убивает runtime (tmux-окно или docker-контейнер) и удаляет запись из БД. Необратимо — сначала убедись что это то, что пользователь хочет. Если агент был `permanent` и просто не нужен сейчас — можно оставить остановленным, а не удалять.

## Типовые сценарии

### Сценарий 1: «создай агента для исследований на GLM»

```bash
# 1. Проверь что никто не создан с таким именем
python main.py agent list

# 2. Проверь что провайдер настроен
grep -A4 "zai-glm:" config.yaml

# 3. Создай
python main.py agent create \
    --name researcher \
    --runtime docker \
    --model glm-4.6 \
    --provider zai-glm \
    --type permanent

# 4. Запиши роль в его личную память
python main.py memory remember \
    --agent researcher \
    --key role \
    --value "исследования по security и AI, пишу отчёты в raw/researcher/" \
    --scope private
```

### Сценарий 2: «посмотри что у нас из агентов»

```bash
python main.py agent list
```

Прочитай вывод, верни пользователю краткую сводку по каждому агенту: имя, runtime, статус, провайдер (если виден в лейбле модели).

### Сценарий 3: «смени модель у researcher на anthropic-api»

Смена провайдера у живого агента — это destroy + create, потому что env-переменные провайдера выставляются при старте контейнера и не меняются на лету для docker-runtime.

```bash
# 1. Предупреди пользователя, что потеряешь состояние контейнера (если там было что-то важное — сначала сохранить в raw/researcher/)
# 2. Пересоздай
python main.py agent destroy --name researcher
python main.py agent create \
    --name researcher \
    --runtime docker \
    --model claude-sonnet-4-5 \
    --provider anthropic-api \
    --type permanent
```

Для host-runtime можно применить env без рестарта через `apply_provider_env`, но это внутренний метод — CLI пока его не выставляет.

### Сценарий 4: «очисти всех dynamic агентов»

```bash
python main.py agent list --json | python -c "
import json, sys, subprocess
agents = json.loads(sys.stdin.read())
for a in agents:
    if a['type'] == 'dynamic':
        subprocess.run(['python', 'main.py', 'agent', 'destroy', '--name', a['name']])
"
```

## Чего НЕ делать

- **Не редактируй `core/agent_manager.py`** чтобы «добавить новую логику». Если CLI чего-то не умеет — скажи пользователю, он заведёт отдельный тикет на расширение control-plane.
- **Не пиши SQL напрямую** в `ag-os.db`. Всё через CLI — иначе hot-reload и валидация обходятся.
- **Не создавай агентов с `--runtime host`** без явного запроса пользователя. Host — это мастер-окно, sub-агенты там только в особых случаях.
- **Не удаляй `master`** ни при каких обстоятельствах.

## Связанные скиллы

- `agos-schedule-management` — если после создания агента нужно поставить его на cron
- `agos-vault-curator` — если агенту нужна долговременная knowledge base

## Справка

Полный reference по флагам: `docs/cli-reference.md` раздел `agent`. Список провайдеров и как их настраивать: `docs/quick-start.md` раздел 5.
