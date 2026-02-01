"""Daemon lifecycle management including first-run initialization."""

import shutil
from pathlib import Path

from .pid_manager import PIDManager


def get_runtime_dir() -> Path:
    """Get the runtime directory path."""
    return Path.home() / ".good-night"


def get_defaults_dir() -> Path:
    """Get the defaults directory from the package."""
    # This assumes the package is installed or running from source
    import good_night

    package_dir = Path(good_night.__file__).parent
    # defaults is at the same level as src in the repo
    repo_defaults = package_dir.parent.parent / "defaults"
    if repo_defaults.exists():
        return repo_defaults

    # Fallback for installed package
    return package_dir.parent / "defaults"


def initialize_runtime_dir(runtime_dir: Path | None = None) -> Path:
    """
    Initialize the runtime directory on first run.

    Creates ~/.good-night/ and copies defaults if needed.

    Returns:
        Path to the runtime directory
    """
    if runtime_dir is None:
        runtime_dir = get_runtime_dir()

    # Create runtime directory if it doesn't exist
    if not runtime_dir.exists():
        runtime_dir.mkdir(parents=True)
        _copy_defaults(runtime_dir)

    # Create subdirectories
    for subdir in ["logs", "resolutions", "output/skills"]:
        (runtime_dir / subdir).mkdir(parents=True, exist_ok=True)

    return runtime_dir


def _copy_defaults(runtime_dir: Path) -> None:
    """Copy default files to runtime directory."""
    try:
        defaults_dir = get_defaults_dir()
    except Exception:
        # Fallback: look for defaults relative to this file
        defaults_dir = Path(__file__).parent.parent.parent / "defaults"

    if not defaults_dir.exists():
        # Create minimal defaults if package defaults not found
        _create_minimal_defaults(runtime_dir)
        return

    # Copy all files from defaults
    for item in defaults_dir.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(defaults_dir)
            dest = runtime_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)


def _create_minimal_defaults(runtime_dir: Path) -> None:
    """Create minimal default configuration."""
    config_content = """daemon:
  poll_interval: 60
  dream_interval: 3600
  log_level: INFO

api:
  enabled: true
  host: 127.0.0.1
  port: 7777

provider:
  default: bedrock
  bedrock:
    region: us-east-1
    model: us.anthropic.claude-sonnet-4-5-20250929-v1:0
  anthropic:
    api_key_env: ANTHROPIC_API_KEY
    model: claude-sonnet-4-20250514

enabled:
  connectors:
    - claude-code
  artifacts:
    - claude-skills
  prompts:
    - pattern-detection
    - frustration-signals

dreaming:
  exploration_agents: 1
  historical_lookback: 7
"""
    (runtime_dir / "config.yaml").write_text(config_content)

    # Create subdirectories
    for subdir in ["connectors", "artifacts", "prompts"]:
        (runtime_dir / subdir).mkdir(parents=True, exist_ok=True)


class DaemonLifecycle:
    """Manages daemon lifecycle."""

    def __init__(self, runtime_dir: Path | None = None):
        self.runtime_dir = initialize_runtime_dir(runtime_dir)
        self.pid_manager = PIDManager(self.runtime_dir)

    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self.pid_manager.is_running()

    def get_pid(self) -> int | None:
        """Get daemon PID if running."""
        if self.is_running():
            return self.pid_manager.read_pid()
        return None

    def start(self) -> bool:
        """
        Start the daemon.

        Returns:
            True if started successfully, False if already running
        """
        if self.is_running():
            return False

        self.pid_manager.write_pid()
        return True

    def stop(self, force: bool = False) -> bool:
        """
        Stop the daemon.

        Args:
            force: If True, use SIGKILL instead of SIGTERM

        Returns:
            True if stopped, False if not running
        """
        return self.pid_manager.stop_daemon(force=force)

    def reload(self) -> bool:
        """
        Reload daemon configuration.

        Returns:
            True if signal sent, False if not running
        """
        return self.pid_manager.reload_config()

    def cleanup(self) -> None:
        """Clean up PID file on shutdown."""
        self.pid_manager.remove_pid()

    @property
    def log_file(self) -> Path:
        """Get path to daemon log file."""
        return self.runtime_dir / "logs" / "daemon.log"

    @property
    def config_file(self) -> Path:
        """Get path to config file."""
        return self.runtime_dir / "config.yaml"
