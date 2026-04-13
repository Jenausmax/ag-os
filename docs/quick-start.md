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

## 11. Частые проблемы

| Симптом | Причина | Фикс |
|---|---|---|
| `ValueError: Environment variable 'X' is not set` при создании агента | Переменная не проброшена в процесс AG-OS | Экспортировать в shell (native) или добавить в `.env` и рестартнуть compose (docker) |
| Sub-агент не видит `litellm` | Агент создан до введения `ag-os-net` или `network` оставлен `bridge` | Проверь `docker.defaults.network: "ag-os-net"` в `config.yaml`, пересоздай агента |
| Claude Code CLI падает с `401` на кастомном endpoint | `ANTHROPIC_AUTH_TOKEN` не совпадает с `master_key` litellm | Синхронизируй `LITELLM_KEY` и `general_settings.master_key` |
| Локальная модель «тупит» на tool-use | Модель слабая или контекст 8k | Бери 32B+ Coder-модель, увеличь `num_ctx` |
| `coder-glm` не создаётся, в логах `Unknown model provider` | Опечатка в ключе или провайдер закомментирован | `grep model_provider config.yaml` — сверь ключи |

---

## 12. Что дальше

- Архитектура компонентов и решения — `CLAUDE.md`.
- Тесты — `pytest tests/ -v`.
- Логи Prompt Guard — таблица `guard_logs` в SQLite.
- Расписание cron — TUI, экран `Schedule`.
