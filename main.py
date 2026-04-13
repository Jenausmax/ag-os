import argparse
import asyncio
import logging

from core.config import load_config
from core.agent_manager import AgentManager
from core.models import AgentRuntime
from db.database import Database
from runtime.tmux_runtime import TmuxRuntime
from telegram.bot import create_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ag-os")


async def bootstrap(config_path: str) -> tuple[AgentManager, Database, object]:
    config = load_config(config_path)

    db = Database(config.database.path)
    await db.init()

    tmux = TmuxRuntime(config.agents.session_name)
    manager = AgentManager(
        db=db,
        tmux_runtime=tmux,
        model_providers=config.model_providers,
    )

    master_provider = config.agents.master.model_provider
    manager.validate_provider(master_provider, AgentRuntime.HOST)
    for agent_def in config.agents.permanent:
        runtime_str = agent_def.get("runtime", "host")
        manager.validate_provider(
            agent_def.get("model_provider", ""),
            AgentRuntime(runtime_str),
        )

    master = await manager.get_agent("master")
    if not master:
        await manager.create_agent(
            name="master",
            model=config.agents.master.model,
            runtime=AgentRuntime.HOST,
            agent_type="permanent",
            provider_name=master_provider,
        )
        logger.info("Master agent created (provider=%s)", master_provider or "claude-subscription")
    else:
        manager.apply_provider_env("master", master_provider, AgentRuntime.HOST)

    for agent_def in config.agents.permanent:
        existing = await manager.get_agent(agent_def["name"])
        runtime_enum = AgentRuntime(agent_def.get("runtime", "host"))
        provider = agent_def.get("model_provider", "")
        if not existing:
            await manager.create_agent(
                name=agent_def["name"],
                model=agent_def.get("model", "claude-cli"),
                runtime=runtime_enum,
                agent_type="permanent",
                provider_name=provider,
            )
            logger.info(f"Permanent agent '{agent_def['name']}' created")
        elif runtime_enum == AgentRuntime.HOST:
            manager.apply_provider_env(agent_def["name"], provider, runtime_enum)

    return manager, db, config


async def run_bot(config_path: str):
    manager, _db, config = await bootstrap(config_path)
    app = create_bot(config.telegram, manager)
    logger.info("AG-OS bot starting...")
    await app.run_polling()


async def run_tui(config_path: str):
    manager, _db, _config = await bootstrap(config_path)
    from tui.app import AgOsApp
    app = AgOsApp(manager)
    logger.info("AG-OS TUI starting...")
    await app.run_async()


async def run_all(config_path: str):
    manager, _db, config = await bootstrap(config_path)
    bot_app = create_bot(config.telegram, manager)
    from tui.app import AgOsApp
    tui_app = AgOsApp(manager)
    logger.info("AG-OS starting (bot + TUI)...")
    await asyncio.gather(
        bot_app.run_polling(),
        tui_app.run_async(),
    )


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

    if args.mode == "bot":
        asyncio.run(run_bot(args.config))
    elif args.mode == "tui":
        asyncio.run(run_tui(args.config))
    elif args.mode == "all":
        asyncio.run(run_all(args.config))


if __name__ == "__main__":
    main()
