from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    STOPPED = "stopped"
    IDLE = "idle"
    WORKING = "working"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


class AgentRuntime(str, Enum):
    HOST = "host"
    DOCKER = "docker"


class AgentType(str, Enum):
    PERMANENT = "permanent"
    DYNAMIC = "dynamic"


@dataclass
class AgentConfig:
    name: str
    model: str
    runtime: AgentRuntime = AgentRuntime.HOST
    agent_type: AgentType = AgentType.DYNAMIC
    status: AgentStatus = AgentStatus.STOPPED
    current_task: str = ""
    tmux_window: str = ""
    container_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    docker_config: dict[str, Any] = field(default_factory=dict)

    @property
    def is_running(self) -> bool:
        return self.status in (AgentStatus.IDLE, AgentStatus.WORKING, AgentStatus.AWAITING_CONFIRMATION)
