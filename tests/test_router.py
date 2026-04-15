from tgbot.router import parse_message


def test_parse_tagged_message():
    agent, prompt = parse_message("@jira отчёт за вчера")
    assert agent == "jira"
    assert prompt == "отчёт за вчера"

def test_parse_untagged_message():
    agent, prompt = parse_message("подними агента для ревью")
    assert agent == "master"
    assert prompt == "подними агента для ревью"

def test_parse_tag_with_multiword():
    agent, prompt = parse_message("@code запусти тесты и покажи результат")
    assert agent == "code"
    assert prompt == "запусти тесты и покажи результат"

def test_parse_empty_after_tag():
    agent, prompt = parse_message("@jira")
    assert agent == "jira"
    assert prompt == ""

def test_parse_tag_case_insensitive():
    agent, prompt = parse_message("@JIRA отчёт")
    assert agent == "jira"
    assert prompt == "отчёт"
