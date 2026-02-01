"""YAML-based configuration."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DaemonSettings:
    poll_interval: int = 60
    dream_interval: int = 3600
    log_level: str = "INFO"


@dataclass
class APISettings:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 7777


@dataclass
class AnthropicSettings:
    api_key_env: str = "ANTHROPIC_API_KEY"
    model: str = "claude-sonnet-4-20250514"


@dataclass
class BedrockSettings:
    region: str = "us-east-1"
    model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


@dataclass
class ProviderSettings:
    default: str = "bedrock"
    anthropic: AnthropicSettings = field(default_factory=AnthropicSettings)
    bedrock: BedrockSettings = field(default_factory=BedrockSettings)


@dataclass
class DreamingSettings:
    exploration_agents: int = 1
    historical_lookback: int = 7
    initial_lookback_days: int = 7  # Days to look back on first run


@dataclass
class EnabledComponents:
    connectors: list[str] = field(default_factory=lambda: ["claude-code"])
    # artifacts: removed - if .md file exists in ~/.good-night/artifacts/, it's enabled
    prompts: list[str] = field(default_factory=lambda: ["pattern-detection", "frustration-signals"])


@dataclass
class Config:
    daemon: DaemonSettings = field(default_factory=DaemonSettings)
    api: APISettings = field(default_factory=APISettings)
    provider: ProviderSettings = field(default_factory=ProviderSettings)
    enabled: EnabledComponents = field(default_factory=EnabledComponents)
    dreaming: DreamingSettings = field(default_factory=DreamingSettings)


def load_config(runtime_dir: Path | None = None) -> Config:
    """Load configuration from YAML file."""
    if runtime_dir is None:
        runtime_dir = Path.home() / ".good-night"

    config_path = runtime_dir / "config.yaml"

    if not config_path.exists():
        return Config()

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    return _parse_config(data)


def _parse_config(data: dict[str, Any]) -> Config:
    """Parse YAML data into Config object."""
    config = Config()

    if "daemon" in data:
        d = data["daemon"]
        config.daemon = DaemonSettings(
            poll_interval=d.get("poll_interval", 60),
            dream_interval=d.get("dream_interval", 3600),
            log_level=d.get("log_level", "INFO"),
        )

    if "api" in data:
        a = data["api"]
        config.api = APISettings(
            enabled=a.get("enabled", True),
            host=a.get("host", "127.0.0.1"),
            port=a.get("port", 7777),
        )

    if "provider" in data:
        p = data["provider"]
        anthropic = AnthropicSettings()
        bedrock = BedrockSettings()

        if "anthropic" in p:
            ap = p["anthropic"]
            anthropic = AnthropicSettings(
                api_key_env=ap.get("api_key_env", "ANTHROPIC_API_KEY"),
                model=ap.get("model", "claude-sonnet-4-20250514"),
            )

        if "bedrock" in p:
            bp = p["bedrock"]
            bedrock = BedrockSettings(
                region=bp.get("region", "us-east-1"),
                model=bp.get("model", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
            )

        config.provider = ProviderSettings(
            default=p.get("default", "bedrock"),
            anthropic=anthropic,
            bedrock=bedrock,
        )

    if "enabled" in data:
        e = data["enabled"]
        config.enabled = EnabledComponents(
            connectors=e.get("connectors", ["claude-code"]),
            # artifacts: removed - scanned from ~/.good-night/artifacts/ directory
            prompts=e.get("prompts", ["pattern-detection", "frustration-signals"]),
        )

    if "dreaming" in data:
        dr = data["dreaming"]
        config.dreaming = DreamingSettings(
            exploration_agents=dr.get("exploration_agents", 1),
            historical_lookback=dr.get("historical_lookback", 7),
            initial_lookback_days=dr.get("initial_lookback_days", 7),
        )

    return config
