from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class TelegramConfig:
    token: str = ""
    allowed_users: list[int] = field(default_factory=list)

@dataclass
class AgentDef:
    name: str = "master"
    model: str = "claude-cli"
    runtime: str = "host"
    type: str = "permanent"
    model_provider: str = ""

@dataclass
class AgentsConfig:
    session_name: str = "ag-os"
    master: AgentDef = field(default_factory=AgentDef)
    permanent: list[dict] = field(default_factory=list)

@dataclass
class DockerDefaults:
    cpus: int = 2
    memory: str = "4g"
    network: str = "ag-os-net"
    workspace_base: str = "/data/ag-os/workspaces"
    shared_dir: str = "/data/ag-os/shared"

@dataclass
class DockerConfig:
    defaults: DockerDefaults = field(default_factory=DockerDefaults)

@dataclass
class GuardConfig:
    enabled: bool = True
    llm_enabled: bool = True
    haiku_api_key: str = ""
    model_provider: str = ""

@dataclass
class DatabaseConfig:
    path: str = "ag-os.db"

@dataclass
class AppConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    guard: GuardConfig = field(default_factory=GuardConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    model_providers: dict = field(default_factory=dict)

def _dict_to_dataclass(cls, data: dict):
    if data is None:
        return cls()
    fieldtypes = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for key, value in data.items():
        if key in fieldtypes and isinstance(value, dict):
            field_cls = cls.__dataclass_fields__[key].type
            if isinstance(field_cls, str):
                field_cls = eval(field_cls)
            if hasattr(field_cls, "__dataclass_fields__"):
                kwargs[key] = _dict_to_dataclass(field_cls, value)
            else:
                kwargs[key] = value
        elif key in fieldtypes:
            kwargs[key] = value
    return cls(**kwargs)

def load_config(path: str) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}
    return _dict_to_dataclass(AppConfig, raw)
