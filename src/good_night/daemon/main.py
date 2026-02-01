"""Main daemon entry point and event loop."""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

from ..config import load_config
from .lifecycle import DaemonLifecycle, initialize_runtime_dir

logger = logging.getLogger("good-night")


class GoodNightDaemon:
    """Main daemon class that runs the dreaming cycles."""

    def __init__(self, runtime_dir: Path | None = None, foreground: bool = False):
        self.runtime_dir = initialize_runtime_dir(runtime_dir)
        self.lifecycle = DaemonLifecycle(self.runtime_dir)
        self.foreground = foreground
        self.config = load_config(self.runtime_dir)
        self._running = False
        self._reload_requested = False
        self._last_dream_time: datetime | None = None

        self._setup_logging()

    def _setup_logging(self) -> None:
        """Set up daemon logging."""
        log_level = getattr(logging, self.config.daemon.log_level.upper(), logging.INFO)

        # Configure root logger
        logger.setLevel(log_level)

        # File handler
        log_file = self.lifecycle.log_file
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)

        # Console handler if in foreground mode
        if self.foreground:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            logger.addHandler(console_handler)

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def handle_sigterm(signum: int, frame: object) -> None:
            logger.info("Received SIGTERM, shutting down...")
            self._running = False

        def handle_sighup(signum: int, frame: object) -> None:
            logger.info("Received SIGHUP, reloading configuration...")
            self._reload_requested = True

        signal.signal(signal.SIGTERM, handle_sigterm)
        signal.signal(signal.SIGINT, handle_sigterm)
        signal.signal(signal.SIGHUP, handle_sighup)

    def _reload_config(self) -> None:
        """Reload configuration from disk."""
        try:
            self.config = load_config(self.runtime_dir)
            self._setup_logging()
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")

    def _should_dream(self) -> bool:
        """Check if it's time to run a dreaming cycle."""
        if self._last_dream_time is None:
            return True

        interval = timedelta(seconds=self.config.daemon.dream_interval)
        return datetime.now() - self._last_dream_time >= interval

    async def _run_dreaming_cycle(self) -> None:
        """Run a single dreaming cycle."""
        from ..dreaming.orchestrator import DreamingOrchestrator

        logger.info("Starting dreaming cycle...")
        try:
            orchestrator = DreamingOrchestrator(self.runtime_dir, self.config)
            await orchestrator.run()
            self._last_dream_time = datetime.now()
            logger.info("Dreaming cycle completed")
        except Exception as e:
            logger.exception(f"Dreaming cycle failed: {e}")

    async def _main_loop(self) -> None:
        """Main daemon loop."""
        self._running = True
        logger.info("Good Night daemon started")

        while self._running:
            # Check for config reload
            if self._reload_requested:
                self._reload_config()
                self._reload_requested = False

            # Check if it's time to dream
            if self._should_dream():
                await self._run_dreaming_cycle()

            # Sleep for poll interval
            await asyncio.sleep(self.config.daemon.poll_interval)

        logger.info("Good Night daemon stopped")

    def run(self) -> int:
        """
        Run the daemon.

        Returns:
            Exit code (0 for success)
        """
        # Check if already running
        if self.lifecycle.is_running():
            logger.error("Daemon is already running")
            return 1

        # Set up signal handlers
        self._setup_signal_handlers()

        # Write PID file
        if not self.lifecycle.start():
            logger.error("Failed to start daemon")
            return 1

        try:
            # Run main loop
            asyncio.run(self._main_loop())
            return 0
        except Exception as e:
            logger.exception(f"Daemon crashed: {e}")
            return 1
        finally:
            self.lifecycle.cleanup()


def run_daemon(runtime_dir: Path | None = None, foreground: bool = False) -> int:
    """
    Run the Good Night daemon.

    Args:
        runtime_dir: Optional runtime directory path
        foreground: If True, run in foreground with console output

    Returns:
        Exit code
    """
    daemon = GoodNightDaemon(runtime_dir=runtime_dir, foreground=foreground)
    return daemon.run()


if __name__ == "__main__":
    sys.exit(run_daemon(foreground=True))
