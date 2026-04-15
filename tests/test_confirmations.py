from tgbot.confirmations import build_confirmation_message, parse_callback_data

def test_build_confirmation_message():
    text, keyboard = build_confirmation_message(agent_name="code", action="git push --force origin main")
    assert "code" in text
    assert "git push --force" in text
    assert len(keyboard) == 1
    assert len(keyboard[0]) == 2

def test_parse_callback_approve():
    result = parse_callback_data("confirm:code:abc123:approve")
    assert result["agent"] == "code"
    assert result["request_id"] == "abc123"
    assert result["action"] == "approve"

def test_parse_callback_deny():
    result = parse_callback_data("confirm:jira:xyz789:deny")
    assert result["agent"] == "jira"
    assert result["action"] == "deny"

def test_parse_callback_invalid():
    result = parse_callback_data("invalid_data")
    assert result is None
