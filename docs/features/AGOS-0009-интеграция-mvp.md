---
id: AGOS-0009
title: Интеграция main.py — запуск MVP
phase: 1 — MVP
status: pending
depends_on: [AGOS-0004, AGOS-0005, AGOS-0006, AGOS-0008]
files_create: []
files_modify: [main.py]
---

## Описание

Интеграция всех компонентов Фазы 1 в main.py. Загрузка конфига, инициализация БД, создание TmuxRuntime и AgentManager, автосоздание мастер-агента и постоянных агентов из конфига, запуск Telegram-бота в режиме polling.

## Acceptance Criteria

- [ ] main.py запускается в режиме bot
- [ ] БД инициализируется, TmuxRuntime создаётся
- [ ] Мастер-агент создаётся автоматически при первом запуске
- [ ] Постоянные агенты из конфига создаются
- [ ] При повторном запуске существующие агенты не дублируются
- [ ] Все тесты Фазы 1 проходят

## Затрагиваемые модули

- main.py: run_bot, main

## Ключевые интерфейсы

```python
async def run_bot(config_path: str)
def main()  # argparse: mode (bot/tui/all), --config
```

## Edge Cases

- Мастер-агент уже существует (повторный запуск)
- Постоянный агент уже существует
- config.yaml не найден — дефолтный конфиг

## План реализации

### Step 1: Обновить main.py с полной интеграцией

```python
# main.py
import argparse
import asyncio
import logging

from core.config import load_config
from core.agent_manager import AgentManager
from db.database import Database
from runtime.tmux_runtime import TmuxRuntime
from telegram.bot import create_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ag-os")


async def run_bot(config_path: str):
    config = load_config(config_path)

    db = Database(config.database.path)
    await db.init()

    tmux = TmuxRuntime(config.agents.session_name)

    manager = AgentManager(db=db, tmux_runtime=tmux)

    # Создать мастер-агента если не существует
    master = await manager.get_agent("master")
    if not master:
        await manager.create_agent(
            name="master",
            model=config.agents.master.model,
            runtime="host",
            agent_type="permanent",
        )
        logger.info("Master agent created")

    # Создать постоянных агентов
    for agent_def in config.agents.permanent:
        existing = await manager.get_agent(agent_def["name"])
        if not existing:
            await manager.create_agent(
                name=agent_def["name"],
                model=agent_def.get("model", "claude-cli"),
                runtime=agent_def.get("runtime", "host"),
                agent_type="permanent",
            )
            logger.info(f"Permanent agent '{agent_def['name']}' created")

    app = create_bot(config.telegram, manager)
    logger.info("AG-OS bot starting...")
    await app.run_polling()


def main():
    parser = argparse.ArgumentParser(description="AG-OS: Multi-agent orchestrator")
    parser.add_argument(
        "mode",
        choices=["bot", "tui", "all"],
        default="bot",
        nargs="?",
        help="Run mode",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file",
    )
    args = parser.parse_args()

    if args.mode in ("bot", "all"):
        asyncio.run(run_bot(args.config))
    elif args.mode == "tui":
        print("TUI mode — coming in Phase 3")


if __name__ == "__main__":
    main()
```

### Step 2: Проверить что всё собирается

```bash
python -c "from core.config import load_config; from core.agent_manager import AgentManager; from db.database import Database; print('OK')"
```

Expected: `OK`

### Step 3: Запустить все тесты

```bash
pytest tests/ -v --tb=short
```

Expected: All passed

### Step 4: Commit

```bash
git add main.py
git commit -m "feat: integrate main.py with bot startup and agent bootstrap"
```
