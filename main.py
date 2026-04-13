import argparse
import asyncio
import logging

from core.config import load_config, GuardConfig
from core.agent_manager import AgentManager
from core.models import AgentRuntime
from db.database import Database
from guard.llm_filter import LlmFilter
from guard.prompt_guard import PromptGuard
from guard.regex_filter import RegexFilter
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


def _build_guard(cfg: GuardConfig, manager: AgentManager, db: Database) -> PromptGuard | None:
    if not cfg.enabled:
        return None
    regex = RegexFilter("guard/rules.yaml")
    llm: LlmFilter | None = None
    if cfg.llm_enabled:
        if cfg.haiku_api_key and cfg.model_provider:
            raise ValueError(
                "guard: set either 'haiku_api_key' (legacy) or 'model_provider', not both"
            )
        if cfg.model_provider:
            creds = manager.build_llm_credentials(cfg.model_provider)
            llm_kwargs: dict = {
                "api_key": creds["api_key"],
                "base_url": creds["base_url"],
            }
            if creds["model_name"]:
                llm_kwargs["model"] = creds["model_name"]
            llm = LlmFilter(**llm_kwargs)
            logger.info("Guard LLM filter: provider=%s", cfg.model_provider)
        elif cfg.haiku_api_key:
            llm = LlmFilter(api_key=cfg.haiku_api_key)
            logger.info("Guard LLM filter: legacy haiku_api_key (consider migrating to model_provider)")
        else:
            logger.warning(
                "Guard LLM filter enabled but neither 'haiku_api_key' nor 'model_provider' set — "
                "running with regex-only protection"
            )
    return PromptGuard(regex_filter=regex, llm_filter=llm, db=db)


async def run_bot(config_path: str):
    manager, db, config = await bootstrap(config_path)
    guard = _build_guard(config.guard, manager, db)
    app = create_bot(config.telegram, manager, guard=guard)
    logger.info("AG-OS bot starting...")
    await app.run_polling()


async def run_tui(config_path: str):
    manager, _db, _config = await bootstrap(config_path)
    from tui.app import AgOsApp
    app = AgOsApp(manager)
    logger.info("AG-OS TUI starting...")
    await app.run_async()


async def run_all(config_path: str):
    manager, db, config = await bootstrap(config_path)
    guard = _build_guard(config.guard, manager, db)
    bot_app = create_bot(config.telegram, manager, guard=guard)
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
