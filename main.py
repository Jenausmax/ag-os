import argparse
import asyncio
import logging
import os
import signal
from pathlib import Path

from core.config import load_config, GuardConfig, VaultConfig
from core.agent_manager import AgentManager
from core.models import AgentRuntime
from core.vault import init_vault_structure
from db.database import Database
from guard.llm_filter import LlmFilter
from guard.prompt_guard import PromptGuard
from guard.regex_filter import RegexFilter
from runtime.tmux_runtime import TmuxRuntime
from scheduler.scheduler import AgScheduler

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
            extra_args=list(config.agents.master.extra_args),
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
                extra_args=list(agent_def.get("extra_args") or []),
            )
            logger.info(f"Permanent agent '{agent_def['name']}' created")
        elif runtime_enum == AgentRuntime.HOST:
            manager.apply_provider_env(agent_def["name"], provider, runtime_enum)

    # Финальный sweep: любые агенты из БД (включая созданных через CLI вне конфига),
    # чьи tmux-окна или docker-контейнеры не пережили рестарт — пересоздаём runtime.
    for agent_row in await manager.list_agents():
        try:
            if await manager.ensure_runtime(agent_row):
                logger.info("Auto-resurrected runtime for '%s'", agent_row["name"])
        except Exception as e:
            logger.warning("Failed to resurrect agent '%s': %s", agent_row["name"], e)

    if config.vault.enabled:
        agent_names = ["master"] + [a.get("name") for a in config.agents.permanent if a.get("name")]
        init_vault_structure(
            config.vault.base_path,
            agent_names=[n for n in agent_names if n],
            git_enabled=config.vault.git_enabled,
        )
        await _ensure_vault_processing_task(db, config.vault)

    return manager, db, config


VAULT_TASK_MARKER = "[vault-processing]"


async def _ensure_vault_processing_task(db: Database, vault_cfg: VaultConfig) -> None:
    """Создаёт дефолтную cron-задачу для мастера по обработке raw → wiki.

    Идемпотентно: ищет задачу с маркером в промте и не создаёт дубль. Retention
    архива упаковано в тот же промт, чтобы не плодить второй cron.
    """
    existing = await db.fetch_one(
        "SELECT id FROM schedule WHERE prompt LIKE ?",
        (f"%{VAULT_TASK_MARKER}%",),
    )
    if existing:
        return
    prompt = (
        f"{VAULT_TASK_MARKER} Обработай свежие файлы в {vault_cfg.base_path}/raw/*/ "
        f"(кроме archive/): прочитай каждый, реши что заслуживает попадания в wiki — "
        f"создай или обнови страницу в {vault_cfg.base_path}/wiki/ с frontmatter "
        f"(owner, scope, created, tags) и `[[wiki-links]]` где уместно. "
        f"Обработанные файлы перемести в {vault_cfg.base_path}/raw/archive/$(date +%F)/. "
        f"Удали архивы старше {vault_cfg.raw_retention_days} дней. "
        f"В конце сделай git commit с осмысленным сообщением."
    )
    await db.execute(
        "INSERT INTO schedule (cron_expression, agent_name, prompt) VALUES (?, ?, ?)",
        (vault_cfg.processing_cron, "master", prompt),
    )
    logger.info("Default vault processing cron task created (%s)", vault_cfg.processing_cron)


PID_FILE = Path("ag-os.pid")
RELOAD_FLAG = Path(".ag-os-reload")


def _write_pid_file() -> None:
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception as e:
        logger.warning("Failed to write pid file %s: %s", PID_FILE, e)


def _remove_pid_file() -> None:
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception as e:
        logger.warning("Failed to remove pid file %s: %s", PID_FILE, e)


def _install_reload_handler(scheduler: AgScheduler) -> asyncio.Task | None:
    """Подвязывает hot-reload шедулера под SIGUSR1 (Unix) или файл-флаг (Windows).

    Возвращает фоновую задачу-вотчер (только на Windows), чтобы её можно было
    отменить при shutdown.
    """
    loop = asyncio.get_running_loop()

    async def _do_reload():
        try:
            report = await scheduler.reload_from_db()
            if report.changed:
                logger.info(
                    "hot-reload: added=%s removed=%s updated=%s",
                    report.added, report.removed, report.updated,
                )
        except Exception as e:
            logger.error("hot-reload failed: %s", e)

    if hasattr(signal, "SIGUSR1"):
        def _handler():
            asyncio.ensure_future(_do_reload())
        try:
            loop.add_signal_handler(signal.SIGUSR1, _handler)
            logger.info("Hot-reload installed on SIGUSR1")
        except NotImplementedError:
            logger.warning("loop.add_signal_handler not supported; hot-reload disabled")
        return None

    # Windows fallback — файл-флаг
    async def _watcher():
        try:
            RELOAD_FLAG.unlink(missing_ok=True)
        except Exception:
            pass
        poll = 5.0
        logger.info("Hot-reload installed on file flag %s (poll=%ss)", RELOAD_FLAG, poll)
        while True:
            try:
                await asyncio.sleep(poll)
                if RELOAD_FLAG.exists():
                    RELOAD_FLAG.unlink(missing_ok=True)
                    await _do_reload()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("reload watcher error: %s", e)

    return loop.create_task(_watcher())


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
    from tgbot.bot import create_bot
    manager, db, config = await bootstrap(config_path)
    guard = _build_guard(config.guard, manager, db)
    scheduler = AgScheduler(db=db, agent_manager=manager)
    await scheduler.start()
    watcher = _install_reload_handler(scheduler)
    _write_pid_file()
    app = create_bot(config.telegram, manager, guard=guard, scheduler=scheduler)
    logger.info("AG-OS bot starting...")
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()
    finally:
        if app.updater and app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()
        if watcher is not None:
            watcher.cancel()
        try:
            scheduler.stop()
        except Exception as e:
            logger.warning("Scheduler shutdown error: %s", e)
        _remove_pid_file()


async def run_tui(config_path: str):
    manager, _db, _config = await bootstrap(config_path)
    from tui.app import AgOsApp
    app = AgOsApp(manager)
    logger.info("AG-OS TUI starting...")
    await app.run_async()


async def run_all(config_path: str):
    from tgbot.bot import create_bot
    manager, db, config = await bootstrap(config_path)
    guard = _build_guard(config.guard, manager, db)
    scheduler = AgScheduler(db=db, agent_manager=manager)
    await scheduler.start()
    watcher = _install_reload_handler(scheduler)
    _write_pid_file()
    bot_app = create_bot(config.telegram, manager, guard=guard, scheduler=scheduler)
    from tui.app import AgOsApp
    tui_app = AgOsApp(manager)
    logger.info("AG-OS starting (bot + TUI)...")
    try:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling()
        await tui_app.run_async()
    finally:
        if bot_app.updater and bot_app.updater.running:
            await bot_app.updater.stop()
        if bot_app.running:
            await bot_app.stop()
        await bot_app.shutdown()
        if watcher is not None:
            watcher.cancel()
        try:
            scheduler.stop()
        except Exception as e:
            logger.warning("Scheduler shutdown error: %s", e)
        _remove_pid_file()


def main():
    parser = argparse.ArgumentParser(description="AG-OS: Multi-agent orchestrator")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")

    sub = parser.add_subparsers(dest="mode")
    sub.add_parser("bot", help="Run Telegram bot")
    sub.add_parser("tui", help="Run TUI dashboard")
    sub.add_parser("all", help="Run bot + TUI in parallel")

    from cli.commands import register_cli_parsers, run as cli_run
    register_cli_parsers(sub)

    args = parser.parse_args()
    mode = args.mode or "bot"

    if mode == "bot":
        asyncio.run(run_bot(args.config))
    elif mode == "tui":
        asyncio.run(run_tui(args.config))
    elif mode == "all":
        asyncio.run(run_all(args.config))
    else:
        raise SystemExit(cli_run(args))


if __name__ == "__main__":
    main()
