"""PID file management for daemon lifecycle."""

import os
import signal
from pathlib import Path


class PIDManager:
    """Manages PID file for daemon process."""

    def __init__(self, runtime_dir: Path):
        self.pid_file = runtime_dir / "good-night.pid"

    def write_pid(self) -> None:
        """Write current process PID to file."""
        self.pid_file.write_text(str(os.getpid()))

    def read_pid(self) -> int | None:
        """Read PID from file, return None if not exists."""
        if not self.pid_file.exists():
            return None
        try:
            return int(self.pid_file.read_text().strip())
        except (ValueError, OSError):
            return None

    def remove_pid(self) -> None:
        """Remove PID file."""
        if self.pid_file.exists():
            self.pid_file.unlink()

    def is_running(self) -> bool:
        """Check if daemon is running."""
        pid = self.read_pid()
        if pid is None:
            return False

        try:
            # Check if process exists
            os.kill(pid, 0)
            return True
        except OSError:
            # Process doesn't exist, clean up stale PID file
            self.remove_pid()
            return False

    def stop_daemon(self, force: bool = False) -> bool:
        """
        Stop the running daemon.

        Args:
            force: If True, use SIGKILL instead of SIGTERM

        Returns:
            True if daemon was stopped, False if it wasn't running
        """
        pid = self.read_pid()
        if pid is None:
            return False

        if not self.is_running():
            return False

        try:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)
            self.remove_pid()
            return True
        except OSError:
            return False

    def reload_config(self) -> bool:
        """
        Send SIGHUP to daemon to reload configuration.

        Returns:
            True if signal was sent, False if daemon not running
        """
        pid = self.read_pid()
        if pid is None or not self.is_running():
            return False

        try:
            os.kill(pid, signal.SIGHUP)
            return True
        except OSError:
            return False
