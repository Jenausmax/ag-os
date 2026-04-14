---
id: AGOS-0031
title: Obsidian vault как knowledge base (raw → wiki pipeline)
phase: 8 — Knowledge Base
status: completed
depends_on: [AGOS-0018, AGOS-0027, AGOS-0028]
files_create: [core/vault.py, tests/test_vault.py, docs/features/AGOS-0031-obsidian-vault.md]
files_modify: [core/config.py, config.yaml, runtime/docker_runtime.py, main.py, cli/commands.py, docs/quick-start.md, docs/cli-reference.md, tests/test_docker_runtime.py, tests/test_cli.py]
---

## Описание

Второй слой памяти поверх существующей SQLite — Obsidian-vault как knowledge base с архитектурой **raw → wiki**:

- `raw/<agent>/` — личный блокнот каждого агента. Sub-агенты в docker получают свою поддиректорию смонтированной как `rw`, всё остальное — read-only.
- `wiki/` — курированные заметки. **Single-writer:** только мастер записывает. На уровне docker это enforced физически через `ro` mount у sub-агентов.
- `raw/archive/YYYY-MM-DD/` — куда мастер перемещает обработанные raw-файлы после ночного прохода.

Мастер раз в сутки (дефолт `0 3 * * *`) читает raw, решает что достойно wiki, создаёт/обновляет wiki-заметки с frontmatter и `[[links]]`, архивирует raw. Это обычный cron-таск через планировщик AGOS-0027, промт создаётся автоматически в bootstrap при первом старте.

SQLite `MemorySystem` остаётся без изменений — она держит runtime state (TTL, scoped key=value для преамбулы промта). Vault — для долгоживущих структурированных заметок, которые человек хочет видеть через Obsidian и граф связей.

## Acceptance Criteria

- [x] `VaultConfig` в `core/config.py` с полями enabled / base_path / raw_retention_days / processing_cron / git_enabled
- [x] `core/vault.py` — `init_vault_structure` (идемпотентный), `agent_raw_dir`, `wiki_dir`
- [x] Структура: `raw/`, `raw/archive/`, `raw/master/`, `raw/<agent>/` для каждого permanent-агента, `wiki/projects|ideas|experiments|people/`, `journal/`
- [x] `DockerRuntime.create_agent` — mount `vault/raw/<name>` rw + `vault/wiki` ro, только если `vault_base` задан
- [x] `main.py bootstrap` — `init_vault_structure` если vault.enabled, опциональный `git init`, создание дефолтной cron-задачи мастера для processing с идемпотентным маркером
- [x] CLI: `python main.py vault init [--force]`, `python main.py vault path --agent X [--wiki]`
- [x] Тесты: инициализация структуры (6), docker mount-схема (2), CLI команды (3)
- [x] Документация: секция в quick-start, строки в cli-reference

## Single-writer гарантия

Конкурентность решена физически, а не кодом:

1. Каждый sub-агент пишет **только** в свою `raw/<name>/` через rw mount → коллизий файловых путей не бывает, потому что разные префиксы.
2. Wiki для sub-агентов смонтирован `ro` → `open(..., 'w')` даст `EROFS`. Никакого дисциплинарного кода не нужно.
3. Мастер — единственный процесс в tmux, серийный Claude Code CLI. Обрабатывает raw в один поток, пишет wiki последовательно. Гонки между мастер-тиками невозможны.

## Асинхронность записи

Sub-агент пишет в raw мгновенно (обычный файловый вызов), но его заметка попадает в wiki **только после следующего processing-тика** (по умолчанию раз в сутки в 03:00). Это осознанный компромисс: batch-обработка мастером через LLM даёт лучшее курирование и связи между заметками, чем запись по одной. При необходимости ручной триггер: `@master обработай raw сейчас` в Telegram.

## Edge Cases

- **Git не установлен** → `git init` ловит `FileNotFoundError`, логирует warning, vault работает без истории.
- **Vault.enabled=false** → bootstrap пропускает инициализацию и cron, DockerRuntime не монтирует vault. CLI `vault init` падает без `--force`.
- **Agent удалён**, а его `raw/<name>/` остался → мастер обрабатывает как обычные файлы при следующем проходе, не зависит от существования агента.
- **Git-конфликты при параллельной правке в Obsidian app + мастер** → классическая проблема shared doc, решается либо дисциплиной (не открывать Obsidian во время processing), либо merge руками. Документировано.
- **Bootstrap-уровень `_ensure_vault_processing_task` запускается повторно** → проверяется по маркеру `[vault-processing]` в промте, дубль не создаётся.

## Что НЕ сделано в этой итерации (вне скоупа)

- Автоматический git-коммит после processing — делегирован промту мастера (он сам вызовет `git -C vault commit`).
- Retention архива — тоже в промте мастера (`rm -rf` archive/* старше N дней).
- TUI-экран для просмотра vault — не нужен, есть Obsidian.
- Merge-тулинг для параллельных правок — не нужен, дисциплина.
