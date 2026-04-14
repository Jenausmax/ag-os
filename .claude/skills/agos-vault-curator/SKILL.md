---
name: agos-vault-curator
description: >
  Управление Obsidian knowledge base (vault) AG-OS: raw-блокноты агентов и
  курированная wiki. Используй этот скилл, когда пользователь просит записать
  идею в vault, создать заметку, обработать raw-блокноты, "промотри записи
  агентов за сегодня", "создай wiki-страницу про X", "что у нас в блокнотах",
  "обнови заметку про проект Y", "свяжи эти заметки", "сделай backlinks".
  Триггерится также когда сам мастер хочет записать наблюдение или вывод,
  чтобы оно не потерялось после рестарта.
---

# AG-OS: куратор Obsidian vault

Этот скилл — для работы с vault (knowledge base слой поверх SQLite-памяти). Мастер здесь играет роль **librarian'а**: sub-агенты пишут черновики в свои `raw/<имя>/`, мастер раз в сутки (или по запросу) обрабатывает их и курирует в `wiki/` с фронтматтером и `[[links]]`.

## Архитектура

```
vault/
├── raw/
│   ├── master/            ← свои черновики (пиши сюда свои наблюдения)
│   ├── <agent-name>/      ← блокноты sub-агентов, read-only для тебя через ls
│   └── archive/YYYY-MM-DD/
├── wiki/
│   ├── projects/
│   ├── ideas/
│   ├── experiments/
│   └── people/
├── journal/               ← ежедневные логи
└── .git/                  ← история (если git_enabled)
```

**Single-writer guarantee:** ТОЛЬКО ты (мастер) записываешь в `wiki/`. Sub-агенты физически не могут — у них `ro` mount. Это значит: вся ответственность за качество wiki на тебе.

## Узнай путь к vault

Не хардкодь — спроси CLI:

```bash
VAULT_BASE=$(python main.py vault path --wiki | xargs dirname)
echo $VAULT_BASE
# например: /data/ag-os/vault
```

Или читай `config.yaml`:

```bash
grep -A1 "^vault:" config.yaml | grep base_path
```

## Типовые сценарии

### Сценарий 1: «запиши идею X в vault»

Если это именно **идея / мысль** (не структурированный факт) — кидай в свой raw, через сутки обработаешь или раньше, если попросят:

```bash
cat > "$VAULT_BASE/raw/master/idea-$(date +%Y-%m-%d-%H%M)-prompt-caching.md" <<'EOF'
# Идея: использовать prompt caching для guard

Если гонять guard-фильтр через anthropic-compatible провайдера с prompt caching,
можно сэкономить до 80% токенов на system-промте (он статичный между вызовами).

## Связанное
- Вчерашнее обсуждение про оптимизацию трат
- AGOS-0026 — guard на альтернативной модели

## Статус
идея, не проверено
EOF
```

**Имя файла** — читаемое и уникальное: `<тип>-<дата>-<слуг>.md`. Так потом проще находить через `ls -t`.

### Сценарий 2: «обработай raw → wiki»

Это главная задача куратора. Автоматически запускается ночью по cron-задаче с маркером `[vault-processing]`, но можно и вручную.

**Алгоритм:**

1. **Собери входящее:**
   ```bash
   find "$VAULT_BASE/raw" -type f -name "*.md" ! -path "*/archive/*" -mtime -2
   ```

2. **Прочитай каждый файл** и классифицируй:
   - **Мусор / шум** → сразу `mv` в `raw/archive/$(date +%F)/`, в wiki не идёт.
   - **Факт или наблюдение** → найди или создай страницу в `wiki/`, добавь раздел/пункт, поставь дату. Поищи что похожее уже есть: `grep -r "тема" "$VAULT_BASE/wiki/"`.
   - **Новая идея или концепция** → создай новую страницу в нужной подпапке (`wiki/ideas/`, `wiki/experiments/`, ...).

3. **Всегда добавляй фронтматтер** к новым wiki-файлам:
   ```yaml
   ---
   owner: <имя агента чей raw был источником, или master если твоё>
   scope: global            # private | shared | global
   shared_with: []          # для scope: shared — список имён агентов
   tags: [tag1, tag2]
   created: 2026-04-14T12:00:00+03:00
   updated: 2026-04-14T12:00:00+03:00
   sources: [raw/master/idea-2026-04-14-1200-prompt-caching.md]
   ---
   ```

4. **Строй связи.** Это главная ценность Obsidian: `[[wiki-link]]` к связанным страницам. Не ленись — один backlink важнее трёх параграфов prose. После обработки пройди свежесозданные страницы и добавь `## Связанное` в конце.

5. **Перемести обработанное в архив:**
   ```bash
   ARCHIVE="$VAULT_BASE/raw/archive/$(date +%F)"
   mkdir -p "$ARCHIVE"
   mv "$VAULT_BASE/raw/master/idea-..." "$ARCHIVE/"
   ```

6. **Ретенция.** Удали архивы старше `raw_retention_days` дней (дефолт 30):
   ```bash
   find "$VAULT_BASE/raw/archive" -type d -mtime +30 -exec rm -rf {} +
   ```

7. **Git commit:**
   ```bash
   cd "$VAULT_BASE"
   git add -A
   git commit -m "vault processing $(date +%F): обработано N черновиков"
   ```

### Сценарий 3: «покажи заметки агента researcher за сегодня»

```bash
find "$VAULT_BASE/raw/researcher" -type f -newer "$(date -d 'today 00:00' +%s)" -name "*.md"
# и прочитай их содержимое через Read tool
```

Сформируй краткую сводку пользователю.

### Сценарий 4: «создай wiki-страницу про проект AG-OS»

```bash
cat > "$VAULT_BASE/wiki/projects/ag-os.md" <<'EOF'
---
owner: master
scope: global
tags: [project, ag-os]
created: 2026-04-14T12:00:00+03:00
updated: 2026-04-14T12:00:00+03:00
---

# AG-OS

Мульти-агентный оркестратор, основной агент — Claude Code CLI. Разворачивается на Ubuntu 22.04 VPS, работает 24/7.

## Ключевые компоненты
- [[agent-manager]] — CRUD агентов
- [[prompt-guard]] — двухуровневая защита промтов
- [[scheduler]] — cron-задачи
- [[vault-system]] — этот самый knowledge base

## Связанное
- [[claude-code]]
- [[telegram-bot-integration]]
EOF

cd "$VAULT_BASE" && git add -A && git commit -m "wiki: создал страницу про AG-OS"
```

### Сценарий 5: «свяжи заметки X и Y»

```bash
# 1. Найди обе заметки
grep -rl "X" "$VAULT_BASE/wiki/"
grep -rl "Y" "$VAULT_BASE/wiki/"

# 2. В каждой добавь секцию "## Связанное" с [[link]] на другую
# (через Edit tool)

# 3. Commit
cd "$VAULT_BASE" && git add -A && git commit -m "wiki: связал X с Y"
```

## Правила качества wiki

1. **Один факт — одна страница.** Не делай «dump.md» со всем подряд. Если тема большая — разбивай на страницы и связывай.
2. **Ссылки важнее prose.** Три `[[link]]` и один абзац лучше, чем пять абзацев без ссылок — граф даёт навигацию.
3. **Фронтматтер обязателен.** Без него Obsidian query и автоматические запросы не сработают.
4. **Даты абсолютные.** `created: 2026-04-14`, не «сегодня». Память через неделю не расшифрует «сегодня».
5. **Имена файлов — kebab-case, ASCII.** Обсидиан работает с кириллицей, но инструменты Unix легче с ASCII.
6. **Scope честный.** Если запись реально private — ставь `private`, sub-агенты всё равно читают wiki как `ro`, но `scope` работает как подсказка.

## Чего НЕ делать

- **Не пиши в `raw/<other-agent>/`.** Это их личное пространство. Только свой `raw/master/` или wiki.
- **Не удаляй wiki-файлы без архивирования.** Перед `rm` — хотя бы `git mv` в `wiki/archive/` (создать если нет).
- **Не пере-курируй слишком часто.** Обработка raw — раз в сутки оптимально. Если гонять каждый час — агенты не успеют «подумать» и ты будешь обрабатывать недописанное.
- **Не коммить в середине процесса.** Один processing-проход = один commit в конце. Иначе git-история превращается в кашу.
- **Не трогай `.obsidian/`.** Это конфиг самого приложения, пусть обновляется когда пользователь открывает vault в Obsidian.

## Связанные скиллы

- `agos-agent-management` — если нужно создать агента, который будет писать в свой raw
- `agos-schedule-management` — processing-таск уже поставлена на cron, но можно добавлять свои

## Справка

- Архитектура vault: `docs/quick-start.md` раздел 10.7
- CLI команды vault: `docs/cli-reference.md` раздел `vault`
- Feature-тикет: `docs/features/AGOS-0031-obsidian-vault.md`
