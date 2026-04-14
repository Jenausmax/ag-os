"""CLI control plane: подкоманды agent/schedule/memory.

Запускаются через `python main.py agent ...` и дают мастер-агенту (и пользователю)
стабильный управляющий API без правок кода и прямых INSERT в SQLite.

Все команды ходят в ту же БД, что и живой бот. Изменения в schedule живой бот
подхватит только на рестарте — hot-reload планируется в AGOS-0029.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

from apscheduler.triggers.cron import CronTrigger

from core.agent_manager import AgentManager
from core.config import load_config
from core.models import AgentRuntime
from db.database import Database
from memory.memory import MemorySystem
from runtime.tmux_runtime import TmuxRuntime


async def init_core(
    config_path: str,
    need_tmux: bool = False,
    need_docker: bool = False,
) -> tuple[Database, AgentManager, Any]:
    """Лёгкий init для CLI-команд: без старта шедулера, без создания агентов из конфига.

    Рантаймы инициализируются лениво по потребности. Ошибки инициализации не
    фатальны: если не нужен рантайм — команда пройдёт. Если нужен — упадём при
    первом вызове AgentManager._get_runtime.
    """
    config = load_config(config_path)
    db = Database(config.database.path)
    await db.init()
    tmux = None
    docker = None
    if need_tmux:
        try:
            tmux = TmuxRuntime(config.agents.session_name)
        except Exception as e:
            print(f"WARN: tmux runtime unavailable: {e}", file=sys.stderr)
    if need_docker:
        try:
            from runtime.docker_runtime import DockerRuntime
            dd = config.docker.defaults
            docker = DockerRuntime(
                cpus=dd.cpus,
                memory=dd.memory,
                network=dd.network,
                workspace_base=dd.workspace_base,
                shared_dir=dd.shared_dir,
            )
        except Exception as e:
            print(f"WARN: docker runtime unavailable: {e}", file=sys.stderr)
    manager = AgentManager(
        db=db,
        tmux_runtime=tmux,
        docker_runtime=docker,
        model_providers=config.model_providers,
    )
    return db, manager, config


def _emit(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, default=str))
    else:
        if isinstance(obj, list):
            for item in obj:
                print(item)
        else:
            print(obj)


def _fail(message: str, code: int = 1) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return code


PID_FILE = Path("ag-os.pid")
RELOAD_FLAG = Path(".ag-os-reload")


def _notify_bot() -> None:
    """Попросить живой бот перечитать таблицу schedule.

    Unix — SIGUSR1 в PID из `ag-os.pid`. Windows — touch файла `.ag-os-reload`
    (бот поллит его раз в 5 секунд). Если PID-файла нет или процесс мёртв —
    warning в stderr, без падения: CLI-команда уже успешно изменила БД, бот
    подхватит на рестарте.
    """
    if hasattr(signal, "SIGUSR1"):
        if not PID_FILE.exists():
            print(
                "WARN: bot pid file not found — the running bot (if any) will "
                "pick up the change on restart",
                file=sys.stderr,
            )
            return
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGUSR1)
        except (ProcessLookupError, ValueError, PermissionError) as e:
            print(f"WARN: could not signal bot ({e}); change applied to DB only", file=sys.stderr)
    else:
        try:
            RELOAD_FLAG.touch()
        except Exception as e:
            print(f"WARN: could not create reload flag ({e}); change applied to DB only", file=sys.stderr)


# ─────────────────────────── agent commands ───────────────────────────


async def agent_create(args: argparse.Namespace) -> int:
    try:
        runtime = AgentRuntime(args.runtime)
    except ValueError:
        return _fail(f"unknown runtime: {args.runtime}")
    db, manager, _ = await init_core(
        args.config,
        need_tmux=runtime == AgentRuntime.HOST,
        need_docker=runtime == AgentRuntime.DOCKER,
    )
    try:
        agent = await manager.create_agent(
            name=args.name,
            model=args.model,
            runtime=runtime,
            agent_type=args.type,
            provider_name=args.provider,
        )
        if args.json:
            _emit(dict(agent), True)
        else:
            print(f"created agent '{agent['name']}' (runtime={agent['runtime']}, status={agent['status']})")
        return 0
    except ValueError as e:
        return _fail(str(e))
    finally:
        await db.close()


async def agent_destroy(args: argparse.Namespace) -> int:
    db, manager, _ = await init_core(args.config, need_tmux=True, need_docker=True)
    try:
        agent = await manager.get_agent(args.name)
        if not agent:
            return _fail(f"agent '{args.name}' not found")
        await manager.destroy_agent(args.name)
        print(f"destroyed agent '{args.name}'")
        return 0
    finally:
        await db.close()


async def agent_list(args: argparse.Namespace) -> int:
    db, manager, _ = await init_core(args.config)
    try:
        agents = await manager.list_agents()
        if args.json:
            _emit([dict(a) for a in agents], True)
            return 0
        if not agents:
            print("(no agents)")
            return 0
        for a in agents:
            print(f"{a['name']:20s} {a['runtime']:8s} {a['status']:10s} {a['model']}")
        return 0
    finally:
        await db.close()


# ─────────────────────────── schedule commands ───────────────────────────


async def schedule_add(args: argparse.Namespace) -> int:
    try:
        CronTrigger.from_crontab(args.cron)
    except Exception as e:
        return _fail(f"invalid cron expression: {e}")
    db, manager, _ = await init_core(args.config)
    try:
        agent = await manager.get_agent(args.agent)
        if not agent:
            return _fail(f"agent '{args.agent}' not found")
        # Доступ к AgScheduler через прямой INSERT, потому что в CLI нам не нужен
        # живой APScheduler — живой бот подхватит запись на рестарте (или по
        # AGOS-0029 hot-reload).
        task_id = await db.execute(
            "INSERT INTO schedule (cron_expression, agent_name, prompt) VALUES (?, ?, ?)",
            (args.cron, args.agent, args.prompt),
        )
        _notify_bot()
        if args.json:
            _emit({"id": task_id, "cron": args.cron, "agent": args.agent, "prompt": args.prompt}, True)
        else:
            print(f"schedule task #{task_id} added")
        return 0
    finally:
        await db.close()


async def schedule_list(args: argparse.Namespace) -> int:
    db, _manager, _ = await init_core(args.config)
    try:
        tasks = await db.fetch_all("SELECT * FROM schedule ORDER BY id")
        if args.json:
            _emit([dict(t) for t in tasks], True)
            return 0
        if not tasks:
            print("(no scheduled tasks)")
            return 0
        for t in tasks:
            enabled = "ON" if t.get("enabled") else "OFF"
            print(
                f"#{t['id']:<4} [{enabled}] {t['cron_expression']:18s} "
                f"@{t['agent_name']:15s} → {t['prompt'][:60]}"
            )
        return 0
    finally:
        await db.close()


async def schedule_rm(args: argparse.Namespace) -> int:
    db, _manager, _ = await init_core(args.config)
    try:
        existing = await db.fetch_one("SELECT id FROM schedule WHERE id = ?", (args.id,))
        if not existing:
            return _fail(f"schedule task #{args.id} not found")
        await db.execute("DELETE FROM schedule WHERE id = ?", (args.id,))
        _notify_bot()
        print(f"schedule task #{args.id} removed")
        return 0
    finally:
        await db.close()


async def schedule_run(args: argparse.Namespace) -> int:
    # Для ручного запуска нужен живой runtime — мастер или агент в tmux/docker.
    db, manager, _ = await init_core(args.config, need_tmux=True, need_docker=True)
    try:
        task = await db.fetch_one("SELECT * FROM schedule WHERE id = ?", (args.id,))
        if not task:
            return _fail(f"schedule task #{args.id} not found")
        agent = await manager.get_agent(task["agent_name"])
        if not agent:
            return _fail(f"agent '{task['agent_name']}' no longer exists")
        await manager.send_prompt(task["agent_name"], task["prompt"])
        print(f"schedule task #{args.id} executed (prompt sent to @{task['agent_name']})")
        return 0
    finally:
        await db.close()


# ─────────────────────────── memory commands ───────────────────────────


async def memory_remember(args: argparse.Namespace) -> int:
    db, _manager, _ = await init_core(args.config)
    try:
        memory = MemorySystem(db)
        record_id = await memory.remember(
            owner=args.agent,
            key=args.key,
            value=args.value,
            scope=args.scope,
            ttl=args.ttl,
        )
        if args.json:
            _emit({"id": record_id, "owner": args.agent, "key": args.key, "scope": args.scope}, True)
        else:
            print(f"memory #{record_id} stored for @{args.agent}")
        return 0
    finally:
        await db.close()


async def memory_get(args: argparse.Namespace) -> int:
    db, _manager, _ = await init_core(args.config)
    try:
        memory = MemorySystem(db)
        if args.key:
            row = await memory.recall(args.agent, args.key)
            if not row:
                return _fail(f"no memory for key '{args.key}' accessible by @{args.agent}")
            _emit(dict(row), args.json)
            return 0
        rows = await memory.get_context(args.agent)
        if args.json:
            _emit([dict(r) for r in rows], True)
            return 0
        if not rows:
            print(f"(no memory visible to @{args.agent})")
            return 0
        for r in rows:
            print(f"#{r['id']:<4} [{r['scope']:7s}] {r['key']} = {r['value']}")
        return 0
    finally:
        await db.close()


async def memory_forget(args: argparse.Namespace) -> int:
    db, _manager, _ = await init_core(args.config)
    try:
        memory = MemorySystem(db)
        await memory.forget(args.id)
        print(f"memory #{args.id} forgotten")
        return 0
    finally:
        await db.close()


# ─────────────────────────── argparse wiring ───────────────────────────


def register_cli_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Регистрирует подкоманды agent/schedule/memory в главном argparse."""

    # agent
    agent = subparsers.add_parser("agent", help="Agent management")
    agent_sub = agent.add_subparsers(dest="cmd", required=True)

    ac = agent_sub.add_parser("create", help="Create a new agent")
    ac.add_argument("--name", required=True)
    ac.add_argument("--runtime", choices=["host", "docker"], default="host")
    ac.add_argument("--model", default="claude-cli")
    ac.add_argument("--provider", default="", help="Key from config.model_providers")
    ac.add_argument("--type", choices=["permanent", "dynamic"], default="dynamic")
    ac.add_argument("--json", action="store_true")

    ad = agent_sub.add_parser("destroy", help="Destroy an agent")
    ad.add_argument("--name", required=True)

    al = agent_sub.add_parser("list", help="List agents")
    al.add_argument("--json", action="store_true")

    # schedule
    sch = subparsers.add_parser("schedule", help="Schedule management")
    sch_sub = sch.add_subparsers(dest="cmd", required=True)

    sa = sch_sub.add_parser("add", help="Add a cron task")
    sa.add_argument("--cron", required=True, help='5-field cron, e.g. "0 * * * *"')
    sa.add_argument("--agent", required=True)
    sa.add_argument("--prompt", required=True)
    sa.add_argument("--json", action="store_true")

    sl = sch_sub.add_parser("list", help="List scheduled tasks")
    sl.add_argument("--json", action="store_true")

    sr = sch_sub.add_parser("rm", help="Remove scheduled task")
    sr.add_argument("--id", type=int, required=True)

    srun = sch_sub.add_parser("run", help="Run a scheduled task now")
    srun.add_argument("--id", type=int, required=True)

    # memory
    mem = subparsers.add_parser("memory", help="Memory management")
    mem_sub = mem.add_subparsers(dest="cmd", required=True)

    mr = mem_sub.add_parser("remember", help="Store a memory record")
    mr.add_argument("--agent", required=True)
    mr.add_argument("--key", required=True)
    mr.add_argument("--value", required=True)
    mr.add_argument("--scope", choices=["private", "shared", "global"], default="private")
    mr.add_argument("--ttl", default=None)
    mr.add_argument("--json", action="store_true")

    mg = mem_sub.add_parser("get", help="Recall memory visible to an agent")
    mg.add_argument("--agent", required=True)
    mg.add_argument("--key", default="")
    mg.add_argument("--json", action="store_true")

    mf = mem_sub.add_parser("forget", help="Delete a memory record by id")
    mf.add_argument("--id", type=int, required=True)


_DISPATCH = {
    ("agent", "create"): agent_create,
    ("agent", "destroy"): agent_destroy,
    ("agent", "list"): agent_list,
    ("schedule", "add"): schedule_add,
    ("schedule", "list"): schedule_list,
    ("schedule", "rm"): schedule_rm,
    ("schedule", "run"): schedule_run,
    ("memory", "remember"): memory_remember,
    ("memory", "get"): memory_get,
    ("memory", "forget"): memory_forget,
}


async def dispatch(args: argparse.Namespace) -> int:
    func = _DISPATCH.get((args.mode, args.cmd))
    if func is None:
        return _fail(f"unknown command: {args.mode} {args.cmd}")
    return await func(args)


def run(args: argparse.Namespace) -> int:
    return asyncio.run(dispatch(args))
