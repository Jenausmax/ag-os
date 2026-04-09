from core.models import AgentConfig, AgentStatus, AgentRuntime, AgentType


def test_agent_config_creation():
    agent = AgentConfig(name="jira", model="claude-cli", runtime=AgentRuntime.HOST, agent_type=AgentType.PERMANENT)
    assert agent.name == "jira"
    assert agent.runtime == AgentRuntime.HOST
    assert agent.status == AgentStatus.STOPPED


def test_agent_config_is_running():
    agent = AgentConfig(name="test", model="claude-cli", runtime=AgentRuntime.HOST)
    assert not agent.is_running
    agent.status = AgentStatus.IDLE
    assert agent.is_running


def test_agent_config_docker():
    agent = AgentConfig(name="grok", model="grok", runtime=AgentRuntime.DOCKER, docker_config={"cpus": 1, "memory": "2g"})
    assert agent.runtime == AgentRuntime.DOCKER
    assert agent.docker_config["cpus"] == 1
