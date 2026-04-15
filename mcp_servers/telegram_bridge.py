"""MCP сервер: даёт мастер-агенту инструмент для отправки ответов в Telegram.

Без этого сервера Telegram-бот AG-OS работал односторонне: пользовательский
промт доходил до мастера через tmux send_keys, но ответ мастера оставался
внутри pane и никогда не возвращался в чат. С ним мастер вызывает tool
`telegram_reply(chat_id, text)` — MCP-сервер POSTит через Bot API.

Регистрация у мастера (один раз):

    claude mcp add ag-os-telegram -- /path/to/.venv/bin/python -m mcp_servers.telegram_bridge

Конфигурация (в порядке поиска):
1. Env-переменная `TELEGRAM_BOT_TOKEN`.
2. Env-переменная `AG_OS_CONFIG` → путь к config.yaml, оттуда `telegram.token`.
3. Файл `config.yaml` в текущей рабочей директории.

Для обычного запуска через AG-OS подходит вариант (3): мастер стартует из корня
репозитория, там лежит config.yaml.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("ag-os-telegram")

mcp = FastMCP("ag-os-telegram")

_token_cache: str | None = None


def _load_token() -> str:
    global _token_cache
    if _token_cache:
        return _token_cache

    env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if env_token:
        _token_cache = env_token
        return env_token

    config_path = os.environ.get("AG_OS_CONFIG", "config.yaml")
    path = Path(config_path)
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            token = (data.get("telegram") or {}).get("token", "").strip()
            if token:
                _token_cache = token
                return token
        except Exception as e:
            logger.warning("failed to parse %s: %s", path, e)

    raise RuntimeError(
        "telegram bot token not found; set TELEGRAM_BOT_TOKEN env or ensure "
        "config.yaml has telegram.token"
    )


@mcp.tool()
async def telegram_reply(chat_id: int, text: str) -> dict[str, Any]:
    """Отправить сообщение в Telegram-чат от имени бота AG-OS.

    Используй этот тул, когда хочешь ответить пользователю, чьё сообщение
    обрабатываешь. `chat_id` берётся из префикса `[ag-os chat=<id> user=<name>]`
    в начале входящего промта — AG-OS подставляет его автоматически в каждое
    сообщение.

    Args:
        chat_id: Целочисленный ID чата Telegram (из префикса входящего сообщения).
        text: Текст ответа. Markdown не поддерживается в этой версии — шли plain
            text. Многострочный текст — можно.

    Returns:
        Словарь с `ok: True` и `message_id` отправленного сообщения.
    """
    token = _load_token()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            url,
            json={"chat_id": chat_id, "text": text},
        )
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return {
        "ok": True,
        "message_id": data.get("result", {}).get("message_id"),
    }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
