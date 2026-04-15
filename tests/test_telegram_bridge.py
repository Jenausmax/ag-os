"""Tests for the ag-os-telegram MCP server (AGOS-0036)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import mcp_servers.telegram_bridge as bridge


@pytest.fixture(autouse=True)
def reset_token_cache():
    bridge._token_cache = None
    yield
    bridge._token_cache = None


def test_load_token_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    assert bridge._load_token() == "123:abc"


def test_load_token_from_config_yaml(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    cfg = tmp_path / "config.yaml"
    cfg.write_text('telegram:\n  token: "999:xyz"\n', encoding="utf-8")
    monkeypatch.setenv("AG_OS_CONFIG", str(cfg))
    assert bridge._load_token() == "999:xyz"


def test_load_token_missing_everywhere(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("AG_OS_CONFIG", str(tmp_path / "nope.yaml"))
    monkeypatch.chdir(tmp_path)  # cwd config.yaml тоже отсутствует
    with pytest.raises(RuntimeError, match="telegram bot token not found"):
        bridge._load_token()


def test_load_token_is_cached(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "first:t")
    assert bridge._load_token() == "first:t"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "second:t")
    assert bridge._load_token() == "first:t"  # из кэша


@pytest.mark.asyncio
async def test_telegram_reply_success(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "sk:test")

    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"ok": True, "result": {"message_id": 42}}

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.post = AsyncMock(return_value=fake_response)

    with patch("mcp_servers.telegram_bridge.httpx.AsyncClient", return_value=client):
        result = await bridge.telegram_reply(chat_id=249402107, text="hi")

    assert result == {"ok": True, "message_id": 42}
    url, = client.post.call_args.args
    assert "sk:test" in url
    assert client.post.call_args.kwargs["json"] == {"chat_id": 249402107, "text": "hi"}


@pytest.mark.asyncio
async def test_telegram_reply_api_error(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "sk:test")

    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"ok": False, "description": "bad chat_id"}

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.post = AsyncMock(return_value=fake_response)

    with patch("mcp_servers.telegram_bridge.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="Telegram API error"):
            await bridge.telegram_reply(chat_id=0, text="hi")


# ─────────────────── AGOS-0040: agent name prefix ───────────────────

def test_prefix_with_agent_name_unset(monkeypatch):
    monkeypatch.delenv("AG_OS_AGENT_NAME", raising=False)
    assert bridge._prefix_with_agent_name("hello") == "hello"


def test_prefix_with_agent_name_set(monkeypatch):
    monkeypatch.setenv("AG_OS_AGENT_NAME", "finik")
    prefixed = bridge._prefix_with_agent_name("готов")
    assert prefixed.startswith("🤖 finik")
    assert prefixed.endswith("готов")
    assert "\n\n" in prefixed


def test_prefix_with_agent_name_blank_env_is_noop(monkeypatch):
    monkeypatch.setenv("AG_OS_AGENT_NAME", "   ")
    assert bridge._prefix_with_agent_name("x") == "x"


@pytest.mark.asyncio
async def test_telegram_reply_prepends_agent_name(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999:xyz")
    monkeypatch.setenv("AG_OS_AGENT_NAME", "master")

    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "ok": True,
        "result": {"message_id": 77},
    }
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.post = AsyncMock(return_value=fake_response)

    with patch("mcp_servers.telegram_bridge.httpx.AsyncClient", return_value=client):
        await bridge.telegram_reply(chat_id=42, text="done")

    sent = client.post.call_args.kwargs["json"]
    assert sent["chat_id"] == 42
    assert sent["text"].startswith("🤖 master")
    assert sent["text"].endswith("done")
