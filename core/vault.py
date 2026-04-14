"""Obsidian-vault как knowledge base слой (AGOS-0031).

Архитектура raw → wiki:

- `raw/<agent>/` — личный блокнот каждого агента, куда он пишет черновики.
  В docker-режиме монтируется в sub-агент как rw, остальное — read-only.
- `wiki/` — курированные заметки. Single-writer: только мастер записывает.
- `raw/archive/YYYY-MM-DD/` — обработанные raw-файлы после ночного прохода мастера.
- `journal/` — ежедневные логи мастера.

Конкурентность решается физически: каждый агент пишет в свою поддиректорию,
коллизий файловых путей нет. Wiki неизменна для sub-агентов — `ro` mount в
docker и дисциплина в коде для host-runtime.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


STANDARD_DIRS = (
    "raw",
    "raw/archive",
    "raw/master",
    "wiki",
    "wiki/projects",
    "wiki/ideas",
    "wiki/experiments",
    "wiki/people",
    "journal",
)


def init_vault_structure(base_path: str, agent_names: list[str] | None = None, git_enabled: bool = True) -> Path:
    """Идемпотентно создать структуру vault.

    Безопасно вызывать на каждом bootstrap — существующие директории не трогает,
    недостающие создаёт. При `git_enabled=True` делает `git init` если vault ещё
    не git-репозиторий (для аудита истории заметок).
    """
    base = Path(base_path)
    base.mkdir(parents=True, exist_ok=True)
    for rel in STANDARD_DIRS:
        (base / rel).mkdir(parents=True, exist_ok=True)
    for name in agent_names or []:
        (base / "raw" / name).mkdir(parents=True, exist_ok=True)
    _ensure_gitkeep(base)
    if git_enabled:
        _ensure_git_init(base)
    logger.info("Vault structure ensured at %s", base)
    return base


def _ensure_gitkeep(base: Path) -> None:
    for rel in STANDARD_DIRS:
        d = base / rel
        if not any(d.iterdir()) if d.exists() else False:
            (d / ".gitkeep").touch()


def _ensure_git_init(base: Path) -> None:
    if (base / ".git").exists():
        return
    try:
        subprocess.run(
            ["git", "init", "-q"], cwd=str(base), check=True,
            capture_output=True, text=True,
        )
        logger.info("Initialized git repo in vault at %s", base)
    except FileNotFoundError:
        logger.warning("git not found — vault will not track history")
    except subprocess.CalledProcessError as e:
        logger.warning("git init failed in vault: %s", e.stderr)


def agent_raw_dir(base_path: str, agent_name: str) -> Path:
    """Абсолютный путь до raw-директории конкретного агента."""
    return Path(base_path) / "raw" / agent_name


def wiki_dir(base_path: str) -> Path:
    return Path(base_path) / "wiki"
