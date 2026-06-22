from pathlib import Path

from agent_service.config import AgentSettings
from app.config import Settings


ROOT = Path(__file__).resolve().parents[2]


def test_backend_settings_env_file_is_root_absolute_path():
    env_file = Path(Settings.Config.env_file)

    assert env_file.is_absolute()
    assert env_file == ROOT / ".env"


def test_agent_settings_env_file_is_root_absolute_path():
    env_file = Path(AgentSettings.model_config["env_file"])

    assert env_file.is_absolute()
    assert env_file == ROOT / ".env"
