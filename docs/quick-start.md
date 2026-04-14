# Quick Start — установка, запуск и юзкейсы AG-OS

Этот документ покрывает:

1. Подготовку окружения (Linux / macOS / WSL2 / Windows).
2. Первый запуск в режимах `native` и `docker`.
3. Настройку мульти-модельных провайдеров (Claude подписка, Anthropic API, z.ai, MiniMax, локальная Ollama через LiteLLM).
4. Практические юзкейсы — *что писать, в какой файл, зачем*.

Если что-то из описанного ниже не совпадает с тем, что ты видишь в репо — доверяй коду, а не доке, и открой issue.

---

## 0. Требования

| Компонент | Версия | Зачем |
|---|---|---|
| Python | 3.11+ | рантайм AG-OS (в native-режиме) |
| Docker Engine | 24+ | для `docker`-режима и sub-агентов |
| tmux | любая свежая | для host-runtime мастер-агента |
| Node.js | 20+ | нужен только для установки Claude Code CLI в native-режиме |
| Claude Code CLI | последняя | `npm i -g @anthropic-ai/claude-code` |

В docker-режиме нужен только Docker — остальное уже в образах.

---

## 1. Установка

### Linux / macOS / WSL2

```bash
git clone <repo> ag-os && cd ag-os
bash scripts/setup.sh
```

Скрипт интерактивный. Он спросит:

- **Режим** — `native` или `docker`. Для VPS 24/7 — бери `docker`. Для локальной отладки — `native`.
- **Пути данных** (только docker) — куда складывать `workspaces`, `shared`, `db`. Дефолт `/data/ag-os/*` — эти же пути **должны существовать и совпадать** снаружи и внутри контейнера, иначе sibling-контейнеры агентов сломаются.

После установки:

- `native` — создаст `.venv`, поставит зависимости, соберёт `ag-os-full:latest` (образ для sub-агентов).
- `docker` — соберёт оба образа (`ag-os-full:latest` и `ag-os:latest`), поднимет стек через `docker compose`.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Скрипт детектит WSL2 и Docker Desktop. Рекомендуется путь через **WSL2** — внутри Ubuntu всё поведение идентично Linux-ветке. Docker Desktop работает, но пути `/data/ag-os/*` придётся подменить на windows-volume.

---

## 2. Первый логин Claude Code CLI

Claude Code CLI авторизуется интерактивно — через браузер. Логин хранится в `~/.claude`, в docker-режиме он смонтирован как named volume `claude-config` и переживает рестарты.

**Native:**

```bash
source .venv/bin/activate
claude login
```

**Docker:**

```bash
docker compose run --rm ag-os claude login
```

После этого мастер-агент на подписке заработает.

> Важно: подписочный логин пригоден **только** для агентов без переопределения `ANTHROPIC_BASE_URL`. Для агентов на альтернативных моделях нужен отдельный API-ключ (см. ниже) — подписка туда не распространяется.

---

## 3. Базовая конфигурация — `config.yaml`

Единственный конфиг, который ты редактируешь руками. Путь: корень репозитория (в docker-режиме монтируется в контейнер read-only).

Минимум, без которого бот не стартует:

```yaml
telegram:
  token: "123456:ABC..."          # от @BotFather
  allowed_users: [12345678]       # Telegram user ID; кто не в списке — игнорируется

guard:
  enabled: true
  llm_enabled: true
  haiku_api_key: "sk-ant-..."     # Anthropic API key, нужен только для LLM-фильтра Prompt Guard
```

Остальные секции (`agents`, `docker`, `scheduler`, `database`) имеют разумные дефолты — трогай только если нужно.

---

## 4. Запуск

### Native

```bash
source .venv/bin/activate
python main.py bot  --config config.yaml   # только Telegram-бот
python main.py tui  --config config.yaml   # только TUI-дашборд
python main.py all  --config config.yaml   # бот + TUI параллельно (для отладки)
```

### Docker

```bash
docker compose up -d ag-os              # бот в фоне, рестарт unless-stopped
docker compose logs -f ag-os            # хвост логов
docker compose exec ag-os python main.py tui --config config.yaml   # TUI внутри контейнера
docker compose down                     # остановить
```

---

## 5. Мульти-модельные провайдеры

Каждый **sub-агент** может работать на своей модели. Это делается через переменные окружения, которые AG-OS пробрасывает в контейнер/окно при создании агента. Claude Code CLI уважает:

| Переменная | Назначение |
|---|---|
| `ANTHROPIC_BASE_URL` | куда слать запросы (по умолчанию `https://api.anthropic.com`) |
| `ANTHROPIC_AUTH_TOKEN` | токен для custom-эндпоинта |
| `ANTHROPIC_API_KEY` | ключ для официального Anthropic API |
| `ANTHROPIC_MODEL` | имя модели |
| `ANTHROPIC_SMALL_FAST_MODEL` | опциональная «быстрая» модель для фоновых задач |

В AG-OS это инкапсулировано в **providers** — ты описываешь их один раз в `config.yaml`, а агенты ссылаются по ключу.

### 5.1. Где прописывать провайдеров

Секция `model_providers` в `config.yaml`:

```yaml
model_providers:
  claude-sub:
    provider: "claude_subscription"      # дефолт — CLI логин, никаких env

  anthropic-api:
    provider: "anthropic_api"
    api_key_env: "ANTHROPIC_API_KEY"     # имя env-переменной на хосте
    model_name: "claude-sonnet-4-5"

  zai-glm:
    provider: "anthropic_compatible"
    base_url: "https://<endpoint-из-доки-zai>"
    model_name: "glm-4.6"
    api_key_env: "ZAI_API_KEY"

  minimax:
    provider: "anthropic_compatible"
    base_url: "https://<endpoint-из-доки-minimax>"
    model_name: "MiniMax-M2"
    api_key_env: "MINIMAX_API_KEY"

  ollama-local:
    provider: "anthropic_compatible"
    base_url: "http://litellm:4000"
    model_name: "ollama/llama3.1"
    api_key_env: "LITELLM_KEY"
```

### 5.2. Где лежат сами ключи

**Нигде в `config.yaml`** — только имена env-переменных через `api_key_env`. Значения читаются из окружения процесса AG-OS в момент создания агента. Это даёт:

- секреты не попадают в git;
- ротация ключа не требует перезапуска всего стека, только пересоздания агента;
- один и тот же `config.yaml` безопасно шарится между окружениями.

**Native-режим:** экспортируй перед стартом или положи в `.env` рядом с `main.py`:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ZAI_API_KEY="..."
export LITELLM_KEY="sk-litellm-local-change-me"
python main.py bot --config config.yaml
```

**Docker-режим:** прокинь ключи в сервис `ag-os` через `environment:` или файл `.env`. Docker Compose автоматически читает `./.env` рядом с `docker-compose.yml`:

```
# .env (рядом с docker-compose.yml, в .gitignore)
ANTHROPIC_API_KEY=sk-ant-...
ZAI_API_KEY=...
LITELLM_KEY=sk-litellm-local-change-me
```

И в `docker-compose.yml` сервис `ag-os` уже наследует эти переменные — Compose передаёт их в контейнер автоматически, если ты добавишь `env_file: .env` или `environment:` с явными именами.

> Важно: sub-агенты **не наследуют** env мастер-контейнера автоматически. AG-OS собирает env для каждого агента из `model_providers` и передаёт явно в `containers.run(environment=...)`. Это значит: чтобы `ZAI_API_KEY` долетел до агента, он должен быть виден процессу AG-OS в момент `create_agent`.

### 5.3. Как привязать агента к провайдеру

В секции `agents` ссылайся на провайдера по ключу:

```yaml
agents:
  session_name: "ag-os"
  master:
    name: "master"
    model: "claude-cli"
    runtime: "host"
    type: "permanent"
    model_provider: "claude-sub"    # мастер всегда на подписке
  permanent:
    - name: "coder"
      model: "glm-4.6"
      runtime: "docker"
      type: "permanent"
      model_provider: "zai-glm"
    - name: "local-bot"
      model: "llama3.1"
      runtime: "docker"
      type: "permanent"
      model_provider: "ollama-local"
```

Либо создавай агентов на лету через Telegram-команды (см. юзкейсы ниже) — там `model_provider` передаётся параметром.

---

### 5.4. Мастер-агент на альтернативной модели

Мастер работает на хосте в tmux (`runtime: host`) и долго живёт между рестартами — поэтому его провайдер устроен чуть отличнее, чем у докер-агентов:

- **Выбор провайдера** — то же поле `model_provider` в секции `agents.master`. Дефолт (`claude-sub` или пусто) = классическая подписка через `claude login`.
- **Валидация на старте.** При `python main.py bot` AG-OS проверяет всех провайдеров из конфига до поднятия Telegram: для `anthropic_api` / `anthropic_compatible` — что нужная env-переменная выставлена и что есть `base_url`; для `claude_subscription` — логирует предупреждение, если `~/.claude` отсутствует (не фатально, можно залогиниться позже).
- **Re-apply env при рестарте.** Tmux-окно мастера переживает рестарт AG-OS. При каждом старте менеджер заново делает `export ANTHROPIC_*=...` в окне мастера согласно актуальному конфигу — то есть чтобы переключить мастера на новую модель, достаточно поправить `config.yaml` и рестартнуть AG-OS. Пересоздавать окно руками не нужно.
- **Что НЕ работает автоматически.** Если ты меняешь провайдера у мастера на лету (конфиг → рестарт AG-OS), уже запущенный `claude` внутри окна мастера **продолжит работать со старой конфигурацией** до следующего запуска `claude` в этом окне. Env обновляется на уровне shell-окружения — но процесс, который уже стартовал, перечитывать env не будет. Надёжный способ применить новый провайдер полностью — сделать в окне `Ctrl+D` (выйти из claude), дождаться шелла и снова запустить `claude`. Либо `tmux kill-window master` и рестарт AG-OS — тогда окно создастся заново с нуля.
- **Подписка ↔ API-ключ — взаимоисключающие.** Если выставлен `ANTHROPIC_API_KEY` или `ANTHROPIC_BASE_URL`, Claude Code CLI игнорирует `~/.claude`-логин. Обратно: без env CLI работает на подписке. Держать оба «включёнными» нельзя. Поэтому при переключении мастера с подписки на API (или наоборот) обязательно рестарт процесса `claude` в окне.

**Пример конфига — мастер на z.ai GLM:**

```yaml
agents:
  master:
    name: "master"
    model: "glm-4.6"
    runtime: "host"
    type: "permanent"
    model_provider: "zai-glm"

model_providers:
  zai-glm:
    provider: "anthropic_compatible"
    base_url: "https://<endpoint-из-доки-zai>"
    model_name: "glm-4.6"
    api_key_env: "ZAI_API_KEY"
```

На старте AG-OS увидит, что мастер уже существует в БД, возьмёт `zai-glm` из конфига, соберёт env и пошлёт `export ANTHROPIC_BASE_URL=...`, `export ANTHROPIC_AUTH_TOKEN=...`, `export ANTHROPIC_MODEL=glm-4.6` в окно `master`. Дальше — рестарт `claude` в окне, и он уходит к z.ai.

**Откат на подписку:**

```yaml
agents:
  master:
    model_provider: "claude-sub"
```

Рестарт AG-OS → env не экспортируется (подписочный провайдер = пустой env) → но **старые переменные в окне всё ещё выставлены**, потому что мы не делаем `unset`. Чтобы откат сработал, нужно либо `tmux kill-window master` перед рестартом, либо в окне мастера вручную `unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_MODEL` и рестартнуть `claude`. Это известное ограничение v1.

### 5.5. Prompt Guard на альтернативной модели

LLM-уровень Prompt Guard (`guard/llm_filter.py`) — это Python-SDK-клиент, а не CLI, поэтому правила для него чуть другие, чем для агентов:

- **Провайдер `claude_subscription` не применим.** `claude login` работает только для CLI; SDK Anthropic требует API-ключ. При попытке — fail-fast с понятной ошибкой на старте.
- **`anthropic_api` и `anthropic_compatible` — оба поддерживаются.** Официальный SDK Anthropic (`anthropic.AsyncAnthropic`) принимает `base_url=...`, поэтому z.ai, MiniMax и локальная Ollama через litellm работают **без замены SDK**.
- **Где прописать.** Поле `model_provider` в секции `guard`, ссылающееся на ключ из `model_providers`. Старое поле `haiku_api_key` остаётся для обратной совместимости, но одновременно с `model_provider` использовать нельзя — на старте упадёт с `set either ... or ..., not both`.
- **Если `llm_enabled: true`, но ни `haiku_api_key`, ни `model_provider` не заданы** — AG-OS логирует warning и работает только с regex-фильтром. Никаких крашей, но уровень защиты ниже.

**Пример — Haiku через официальный API:**

```yaml
guard:
  enabled: true
  llm_enabled: true
  model_provider: "anthropic-api"

model_providers:
  anthropic-api:
    provider: "anthropic_api"
    api_key_env: "ANTHROPIC_API_KEY"
    model_name: "claude-haiku-4-5"
```

**Пример — дешёвый GLM через z.ai:**

```yaml
guard:
  enabled: true
  llm_enabled: true
  model_provider: "zai-glm-small"

model_providers:
  zai-glm-small:
    provider: "anthropic_compatible"
    base_url: "https://<endpoint-из-доки-zai>"
    model_name: "glm-4.5-air"
    api_key_env: "ZAI_API_KEY"
```

**Пример — локальная модель через litellm-прокси (full offline):**

```yaml
guard:
  enabled: true
  llm_enabled: true
  model_provider: "ollama-guard"

model_providers:
  ollama-guard:
    provider: "anthropic_compatible"
    base_url: "http://litellm:4000"
    model_name: "ollama/qwen2.5:7b"
    api_key_env: "LITELLM_KEY"
```

**Что важно помнить:**

- Guard вызывается на **каждое** входящее сообщение в Telegram. Бери быструю/дешёвую модель — Haiku, GLM-air, 7B-локалку. Sonnet/Opus здесь оверкилл.
- Guard — не агент. Он не создаёт tmux-окно и не имеет памяти. Вся настройка — через `config.yaml` + env-переменную с ключом, как и для агентов.
- При ошибке LLM-фильтра (таймаут, 5xx от провайдера) промт помечается как `SUSPICIOUS` — fail-safe. Это значит, что упавший гуард-эндпоинт не заблокирует всё общение, но и не пропустит опасное.

## 6. Юзкейс 1: всё на подписке Claude Code (baseline)

**Когда:** ты только начинаешь, хочешь проверить, что стек работает, никаких альтернативных моделей.

**Что делать:**

1. `config.yaml` → оставить `model_providers.claude-sub` как есть; у `master` проставить `model_provider: "claude-sub"`.
2. Запустить `claude login` (один раз).
3. `docker compose up -d ag-os` (или `python main.py bot`).
4. В Telegram — `/create coder` → новый sub-агент в docker, на подписке мастера? **Нет**: sub-агент запускается в отдельном контейнере со своим `~/.claude`. Если хочешь чтобы он тоже ходил на подписку — смонтируй тот же volume `claude-config` и в sub-агенте, **или** используй отдельный API-ключ через провайдера `anthropic-api`.

**Ограничение:** подписочный логин привязан к одному `~/.claude`. Практически — мастер на подписке, sub-агенты на API-ключе.

---

## 7. Юзкейс 2: мастер на подписке, sub-агенты на Anthropic API

**Когда:** хочешь честного sub-агента на `claude-sonnet-4-5`, но без возни с прокси.

**Что делать:**

1. Получить API-ключ в консоли Anthropic.
2. Экспортировать `ANTHROPIC_API_KEY` в окружение AG-OS (в `.env` при docker-режиме).
3. В `config.yaml` раскомментировать провайдера `anthropic-api` и указать его у нужного агента:

   ```yaml
   permanent:
     - name: "researcher"
       model: "claude-sonnet-4-5"
       runtime: "docker"
       model_provider: "anthropic-api"
   ```
4. Рестарт: `docker compose restart ag-os`.

Внутри контейнера `researcher` Claude Code CLI увидит `ANTHROPIC_API_KEY` и пойдёт в api.anthropic.com напрямую.

---

## 8. Юзкейс 3: sub-агент на z.ai (GLM) или MiniMax

**Когда:** хочешь дешевле/быстрее/другая модель, а у провайдера есть anthropic-совместимый эндпоинт специально под Claude Code.

**Что делать:**

1. Зарегистрироваться у провайдера, получить API-ключ и **точный base_url** из их доки раздела *«Claude Code integration»*. URL-ы меняются — не гадай, открой их док.
2. Экспортировать ключ:
   ```bash
   export ZAI_API_KEY="..."      # или MINIMAX_API_KEY
   ```
3. В `config.yaml`:
   ```yaml
   model_providers:
     zai-glm:
       provider: "anthropic_compatible"
       base_url: "https://<endpoint-из-доки>"
       model_name: "glm-4.6"
       api_key_env: "ZAI_API_KEY"

   agents:
     permanent:
       - name: "coder-glm"
         model: "glm-4.6"
         runtime: "docker"
         model_provider: "zai-glm"
   ```
4. Рестарт. Агент `coder-glm` теперь говорит с z.ai, а снаружи он — обычный Claude Code агент: Prompt Guard, память, `@тег` роутинг, всё работает.

**На что смотреть:**

- **Tool-use на длинных цепочках** — GLM/MiniMax заявляют поддержку, но на файловых правках могут спотыкаться. Проверяй на реальной задаче.
- **Контекст** — большой системный промт + tool-results жрут окно. Бери модель с 128k+.
- **Юрисдикция** — не лей туда клиентский код под NDA.

---

## 9. Юзкейс 4: локальная модель через Ollama + LiteLLM

**Когда:** хочешь air-gapped, приватность, или просто чтобы агент крутился на домашней GPU.

**Архитектура:**

```
sub-агент (docker)  →  litellm (docker)  →  host.docker.internal:11434  →  ollama на хосте
    |                       |
    | ANTHROPIC_BASE_URL    | переводит Anthropic-формат в Ollama-формат
    | =http://litellm:4000  |
```

**Что делать:**

1. **На хосте** поставить Ollama и скачать модель:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull llama3.1
   ollama serve   # слушает 11434
   ```

2. **Проверить `deploy/litellm.yaml`** — в репо лежит пример с `ollama/llama3.1` и `ollama/qwen2.5-coder`. Поправь под свои модели. `master_key` — это то, что агент будет отдавать как `ANTHROPIC_AUTH_TOKEN`, синхронизируй со значением `LITELLM_KEY` в `.env`.

3. **Поднять litellm** (профиль `local-models` не стартует по умолчанию):
   ```bash
   docker compose --profile local-models up -d litellm
   ```

4. **Проверить из ag-os-контейнера** (должно вернуть список моделей):
   ```bash
   docker compose exec ag-os curl -s http://litellm:4000/v1/models -H "Authorization: Bearer $LITELLM_KEY"
   ```

5. **Привязать агента** в `config.yaml`:
   ```yaml
   model_providers:
     ollama-local:
       provider: "anthropic_compatible"
       base_url: "http://litellm:4000"
       model_name: "ollama/llama3.1"
       api_key_env: "LITELLM_KEY"

   agents:
     permanent:
       - name: "offline-coder"
         model: "llama3.1"
         runtime: "docker"
         model_provider: "ollama-local"
   ```

6. Рестарт `ag-os`, создать/пересоздать агента.

**Нюансы сети:**

- Все контейнеры (AG-OS, litellm, sub-агенты) сидят в именованной сети `ag-os-net`. `DockerRuntime.network` по умолчанию теперь `ag-os-net` — именно поэтому агент дотягивается до `litellm` по имени сервиса.
- `host.docker.internal:host-gateway` в `docker-compose.yml` нужен, чтобы **litellm** увидел Ollama на хосте. Без этого на Linux `host.docker.internal` не резолвится.
- Если Ollama крутится в другом контейнере, а не на хосте — поправь `api_base` в `deploy/litellm.yaml` на `http://<имя-контейнера>:11434` и подключи его к `ag-os-net`.

**Подводные камни:**

- **CPU-only Ollama** непригодна для agentic-loop — ответ минуту, Telegram таймаутит. Нужен GPU.
- **Tool-use** у мелких моделей (7B-13B) ломается. Бери 70B+ или Qwen2.5-Coder-32B, они заметно стабильнее на function-calling.
- **Окно контекста** — llama3.1 по умолчанию 8k; поставь `num_ctx: 32768` в Modelfile или в Ollama API.

---

## 10. Юзкейс 5: разные агенты — разные модели одновременно

Никаких ограничений — каждый агент независим. Типичный сетап:

```yaml
agents:
  master:
    name: "master"
    runtime: "host"
    model_provider: "claude-sub"       # дорогая мощная модель, принимает решения
  permanent:
    - name: "researcher"               # качественный reasoning
      runtime: "docker"
      model_provider: "anthropic-api"
    - name: "coder"                    # быстрый и дешёвый кодогенератор
      runtime: "docker"
      model_provider: "zai-glm"
    - name: "offline"                  # приватные задачи без выхода в интернет
      runtime: "docker"
      model_provider: "ollama-local"
```

Telegram-роутинг через `@тег` (`@coder напиши регексп для ...`) сам отправит промт нужному агенту на нужной модели. Память, Prompt Guard и Scheduler работают поверх и не зависят от того, какая модель под капотом.

---

## 10.5. Планировщик: cron-задачи для агентов

AG-OS умеет будить агентов по cron-расписанию. Любая задача — это запись в таблице `schedule` с полями: cron-выражение (5 полей, стандартный Unix-формат), имя агента и промт. Когда cron срабатывает, AG-OS зовёт `manager.send_prompt(agent, prompt)` — дальше работает обычный путь через tmux/docker рантайм, Memory и Prompt Guard.

### Когда стартует планировщик

`AgScheduler` поднимается автоматически в режимах `bot` и `all` (но не в `tui` — TUI это дашборд, не runtime). На старте он загружает все включённые записи из таблицы `schedule` и регистрирует их в APScheduler. Grace-shutdown отрабатывает по `Ctrl+C` или `docker compose down`.

### Telegram-команды

| Команда | Что делает |
|---|---|
| `/schedule_add <min> <hour> <day> <month> <dow> @agent <prompt>` | Создаёт задачу. Cron валидируется до записи в БД. |
| `/schedule_list` | Показывает все задачи с id, cron, агентом, последним запуском и результатом. |
| `/schedule_rm <id>` | Удаляет задачу. |
| `/schedule_run <id>` | Немедленно исполняет задачу вручную (для отладки). |

Все команды требуют, чтобы пользователь был в `telegram.allowed_users`.

### Юзкейс: проверка почты раз в час

```
/schedule_add 0 * * * * @master проверь новую почту за последний час и доложи если что-то важное
```

В этот момент в таблице `schedule` появляется запись, APScheduler её сразу регистрирует, и в :00 каждого часа мастер получит этот промт в своё tmux-окно.

**Важный caveat:** планировщик — это **будильник**, а не инструмент для чтения почты. Он передаёт мастеру текст промта. Чтобы мастер *реально* смог прочитать почту, ему нужен соответствующий тул в окружении: MCP gmail-сервер, локальный CLI (`mbsync`/`notmuch`/свой скрипт) или доступ к API. Без этого мастер каждый час честно ответит «у меня нет инструмента для чтения почты». Подключение таких инструментов — отдельная подготовка, не часть AGOS-0027.

### Примеры cron-выражений

| Выражение | Что значит |
|---|---|
| `0 * * * *` | каждый час в :00 |
| `*/15 * * * *` | каждые 15 минут |
| `0 9 * * 1-5` | в 9:00 по будням |
| `0 0 1 * *` | в полночь 1-го числа каждого месяца |
| `30 8,20 * * *` | в 8:30 и 20:30 ежедневно |

### История выполнения

Поля `last_run` и `last_result` (`success` или `error`) пишутся обратно в запись после каждого тика. Видны через `/schedule_list` и в TUI-экране Schedule. Для деталей ошибок смотри логи AG-OS (`docker compose logs -f ag-os` или stdout native-запуска).

### Hot-reload расписания (AGOS-0029)

Начиная с AGOS-0029 живой бот **перечитывает таблицу `schedule` по внешнему сигналу** — не нужно рестартовать, чтобы применить изменения от CLI или прямых SQL-правок.

**Как это работает:**

- На старте `python main.py bot` или `all` AG-OS пишет `ag-os.pid` в рабочую директорию и подписывается на триггер перезагрузки.
- **На Linux / macOS / WSL2** — триггер `SIGUSR1`. CLI-команды (`schedule add`/`rm`) после успешного изменения БД читают PID и шлют сигнал. Бот ловит его, вызывает `scheduler.reload_from_db()`, который идемпотентно сверяет живые джобы с таблицей (diff: added / removed / updated).
- **На Windows** — сигналов нет, используется файл-флаг `.ag-os-reload`. Бот поллит его каждые 5 секунд в фоновой корутине; CLI делает `touch` при изменениях. Задержка до применения — до 5 секунд.

**Типичный флоу:**

```bash
# терминал 1: живой бот
python main.py bot --config config.yaml

# терминал 2: CLI
python main.py schedule add --cron "0 * * * *" --agent master --prompt "проверь почту"
# INFO: hot-reload: added=[5] removed=[] updated=[]   ← видно в логах бота
```

**Нюансы:**

- Если PID-файл отсутствует или процесс мёртв — CLI выдаёт warning `could not signal bot`, но операция в БД уже прошла. Подхватится на следующем рестарте или при ручном `kill -USR1 <pid>`.
- Прямые SQL-правки (`sqlite3 ag-os.db 'INSERT ...'`) подхватываются той же механикой: шлёшь `kill -USR1 $(cat ag-os.pid)` и бот перечитает.
- `reload_from_db` идемпотентен — вызывать можно сколько угодно раз, на стабильное состояние он не реагирует.
- Изменение записи (cron, prompt, agent) через SQL тоже подхватывается: метод сравнивает хранимый снимок с живым и перерегистрирует job, если что-то отличается.

Telegram-команды `/schedule_add` / `/schedule_rm` работают через живой `AgScheduler` напрямую — никакой сигнал им не нужен, изменения видны мгновенно.

## 10.6. Мастер управляет AG-OS (self-automation)

После AGOS-0028 в `python main.py` появились подкоманды для управления агентами, расписанием и памятью. Это даёт мастер-агенту стабильный control-plane: он живёт в tmux на хосте и умеет вызывать bash-команды, значит может выполнять эти же команды по запросу пользователя.

Идея, которая раньше выглядела как «мастер редактирует код шедулера» (опасно и хрупко), теперь раскладывается в три bash-вызова.

### Юзкейс: «создай агента для проверки почты»

Пользователь в Telegram пишет мастеру:

> @master создай агента который будет проверять почту раз в час с mcp gmail

Мастер в своём окне делает:

```bash
# 1. создать docker-агента на anthropic-compatible провайдере
python main.py agent create --name mail-bot --runtime docker --provider zai-glm --type permanent

# 2. записать в его личную память роль и инструкцию по использованию gmail
python main.py memory remember --agent mail-bot --key role --value "проверяю входящую почту" --scope private
python main.py memory remember --agent mail-bot --key mcp --value "gmail через claude mcp" --scope private

# 3. поставить на cron
python main.py schedule add --cron "0 * * * *" --agent mail-bot --prompt "проверь непрочитанную почту за последний час и доложи важное"
```

И отвечает пользователю: «создал mail-bot, поставил на каждый час, требую рестарт AG-OS чтобы задача начала исполняться». После AGOS-0029 рестарт не будет нужен — CLI будет слать `SIGUSR1` живому боту.

### Чем это принципиально отличается от «мастер правит код»

- **Нет hot-reload Python-модулей.** Все изменения идут через данные в SQLite, а не через `importlib.reload`.
- **Нет blast radius.** Мастер не может сломать сам себя: все команды проходят валидацию (cron, агент существует, провайдер валиден).
- **Есть стабильный контракт.** Команды — это API с fail-fast exit-кодами, а не парсинг произвольных kwargs.
- **Аудит из коробки.** Все изменения попадают в БД, а не в файловую систему — можно посмотреть историю через SQL или TUI.

Полная справка по командам — в [docs/cli-reference.md](cli-reference.md).

### Ограничения v1

1. **Нет hot-reload.** Новые cron-записи живой бот подхватит только на рестарте (AGOS-0029 — следующая таска).
2. **Нет CLI для MCP-серверов.** Команды типа `python main.py mcp enable gmail --agent mail-bot` пока нет — MCP подключается вручную через `claude mcp add`. Это отдельный тикет, если станет нужно.
3. **CLI и живой бот — разные процессы.** Для команд, которые трогают runtime (`agent create`, `agent destroy`, `schedule run`), CLI поднимает свой инстанс runtime. Это безопасно, но нужно понимать: если бот упал, его tmux-окна живут — CLI их увидит и будет с ними работать.

## 11. Частые проблемы

| Симптом | Причина | Фикс |
|---|---|---|
| `ValueError: Environment variable 'X' is not set` при создании агента | Переменная не проброшена в процесс AG-OS | Экспортировать в shell (native) или добавить в `.env` и рестартнуть compose (docker) |
| Sub-агент не видит `litellm` | Агент создан до введения `ag-os-net` или `network` оставлен `bridge` | Проверь `docker.defaults.network: "ag-os-net"` в `config.yaml`, пересоздай агента |
| Claude Code CLI падает с `401` на кастомном endpoint | `ANTHROPIC_AUTH_TOKEN` не совпадает с `master_key` litellm | Синхронизируй `LITELLM_KEY` и `general_settings.master_key` |
| Локальная модель «тупит» на tool-use | Модель слабая или контекст 8k | Бери 32B+ Coder-модель, увеличь `num_ctx` |
| `coder-glm` не создаётся, в логах `Unknown model provider` | Опечатка в ключе или провайдер закомментирован | `grep model_provider config.yaml` — сверь ключи |
| Поменял `model_provider` у мастера, но он всё ещё ходит в старую модель | Процесс `claude` в окне мастера был запущен до рестарта и держит старое окружение | `Ctrl+D` в окне мастера → рестарт `claude`, либо `tmux kill-window master` и рестарт AG-OS |
| При старте AG-OS падает с `Environment variable 'X' is not set` | Валидация провайдеров на старте поймала отсутствующий ключ (fail-fast до запуска бота) | Экспортировать переменную в shell (native) или добавить в `.env` и рестартнуть compose |
| В логе `Claude Code CLI не залогинен (~/.claude не существует)` | Провайдер мастера — подписка, но `claude login` не выполнен | Запустить `claude login` в окне мастера один раз (native) или `docker compose run --rm ag-os claude login` |
| `/schedule_add` отвечает «невалидный cron» | Неправильное количество полей или опечатка | 5 полей через пробел: `<мин> <час> <день> <месяц> <день_недели>`. Примеры — в разделе 10.5 |
| Задача в `/schedule_list` есть, но не срабатывает | Поле `enabled = 0` или планировщик не запущен (режим `tui`) | Проверь `enabled`, запускай через `bot` или `all` |
| Мастер каждый час отвечает «у меня нет инструмента для X» | Шедулер его разбудил, но инструмента действительно нет | Подключи MCP-сервер или CLI-утилиту до настройки cron (см. AGOS-0028) |

---

## 12. Что дальше

- Архитектура компонентов и решения — `CLAUDE.md`.
- Тесты — `pytest tests/ -v`.
- Логи Prompt Guard — таблица `guard_logs` в SQLite.
- Расписание cron — TUI, экран `Schedule`.
