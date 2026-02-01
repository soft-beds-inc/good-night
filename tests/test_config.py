"""Tests for configuration parsing."""

from pathlib import Path

from good_night.config import Config, load_config, _parse_config


class TestConfig:
    """Tests for YAML config parsing."""

    def test_parse_empty_dict(self) -> None:
        """Test parsing empty config."""
        config = _parse_config({})

        assert config.daemon.poll_interval == 60
        assert config.daemon.dream_interval == 3600
        assert config.provider.default == "bedrock"

    def test_parse_daemon_settings(self) -> None:
        """Test parsing daemon settings."""
        data = {
            "daemon": {
                "poll_interval": 120,
                "dream_interval": 7200,
                "log_level": "DEBUG",
            }
        }

        config = _parse_config(data)

        assert config.daemon.poll_interval == 120
        assert config.daemon.dream_interval == 7200
        assert config.daemon.log_level == "DEBUG"

    def test_parse_api_settings(self) -> None:
        """Test parsing API settings."""
        data = {
            "api": {
                "enabled": False,
                "host": "0.0.0.0",
                "port": 8080,
            }
        }

        config = _parse_config(data)

        assert config.api.enabled is False
        assert config.api.host == "0.0.0.0"
        assert config.api.port == 8080

    def test_parse_provider_settings(self) -> None:
        """Test parsing provider settings."""
        data = {
            "provider": {
                "default": "anthropic",
                "anthropic": {
                    "model": "claude-opus-4-20250514",
                },
                "bedrock": {
                    "region": "us-west-2",
                    "model": "custom-model",
                },
            }
        }

        config = _parse_config(data)

        assert config.provider.default == "anthropic"
        assert config.provider.anthropic.model == "claude-opus-4-20250514"
        assert config.provider.bedrock.region == "us-west-2"

    def test_parse_enabled_components(self) -> None:
        """Test parsing enabled components."""
        data = {
            "enabled": {
                "connectors": ["claude-code", "other"],
                "artifacts": ["claude-skills"],
                "prompts": ["pattern-detection"],
            }
        }

        config = _parse_config(data)

        assert config.enabled.connectors == ["claude-code", "other"]
        assert config.enabled.artifacts == ["claude-skills"]
        assert config.enabled.prompts == ["pattern-detection"]

    def test_parse_full_config(self) -> None:
        """Test parsing complete configuration."""
        data = {
            "daemon": {
                "poll_interval": 60,
                "dream_interval": 3600,
                "log_level": "INFO",
            },
            "api": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 7777,
            },
            "provider": {
                "default": "bedrock",
            },
            "dreaming": {
                "exploration_agents": 2,
                "historical_lookback": 14,
            },
        }

        config = _parse_config(data)

        assert config.daemon.poll_interval == 60
        assert config.api.enabled is True
        assert config.provider.default == "bedrock"
        assert config.dreaming.exploration_agents == 2
        assert config.dreaming.historical_lookback == 14

    def test_load_config_missing_file(self, tmp_path: Path) -> None:
        """Test loading config when file doesn't exist."""
        config = load_config(tmp_path)

        # Should return default config
        assert config.daemon.poll_interval == 60
        assert config.provider.default == "bedrock"

    def test_load_config_from_yaml(self, tmp_path: Path) -> None:
        """Test loading config from YAML file."""
        config_content = """
daemon:
  poll_interval: 30
provider:
  default: anthropic
"""
        (tmp_path / "config.yaml").write_text(config_content)

        config = load_config(tmp_path)

        assert config.daemon.poll_interval == 30
        assert config.provider.default == "anthropic"
