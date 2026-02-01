"""CLI interface for Good Night."""

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import typer

# Load .env from current directory or parent directories
load_dotenv()
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..config import load_config
from ..daemon.lifecycle import DaemonLifecycle, get_runtime_dir
from ..dreaming.events import AgentEvent

app = typer.Typer(
    name="good-night",
    help="AI reflection system that analyzes conversations and produces artifacts.",
    no_args_is_help=True,
)
console = Console()


def get_lifecycle() -> DaemonLifecycle:
    """Get daemon lifecycle instance."""
    return DaemonLifecycle()


# Event display helpers
ICONS = {
    "tool_call": ">",
    "tool_result": "<",
    "thinking": "~",
    "complete": "+",
    "error": "!",
}

COLORS = {
    "tool_call": "blue",
    "tool_result": "green",
    "thinking": "yellow",
    "complete": "bright_green",
    "error": "red",
}


class LiveEventDisplay:
    """Manages live-updating event display with per-agent status box."""

    def __init__(self):
        self.agent_states: dict[str, AgentEvent] = {}
        self.live: Live | None = None

    def start(self) -> None:
        """Start the live display."""
        self.live = Live(
            self._render(),
            console=console,
            refresh_per_second=4,
            transient=False,
        )
        self.live.start()

    def stop(self) -> None:
        """Stop the live display."""
        if self.live:
            self.live.stop()
            self.live = None

    def on_event(self, event: AgentEvent) -> None:
        """Handle incoming event."""
        self.agent_states[event.agent_id] = event
        if self.live:
            self.live.update(self._render())

    def _render(self) -> Panel:
        """Render the current state as a panel."""
        if not self.agent_states:
            return Panel("Waiting for agents...", title="Dreaming", border_style="dim")

        table = Table.grid(padding=(0, 1))
        table.add_column("Agent", style="cyan", width=20)
        table.add_column("Status", width=60)

        for agent_id, event in self.agent_states.items():
            icon = ICONS.get(event.event_type, ".")
            color = COLORS.get(event.event_type, "white")

            status = Text()
            status.append(icon + " ", style=color)
            status.append(event.summary[:55] + "..." if len(event.summary) > 55 else event.summary)

            table.add_row(agent_id, status)

        return Panel(table, title="Dreaming", border_style="blue")


class SimpleEventDisplay:
    """Simple append-style event display for non-TTY output."""

    def __init__(self):
        pass

    def start(self) -> None:
        """No-op for simple display."""
        pass

    def stop(self) -> None:
        """No-op for simple display."""
        pass

    def on_event(self, event: AgentEvent) -> None:
        """Print event to console."""
        icon = ICONS.get(event.event_type, ".")
        color = COLORS.get(event.event_type, "white")

        text = Text()
        text.append(f"[{event.agent_id}] ", style="dim")
        text.append(icon + " ", style=color)
        text.append(event.summary)

        console.print(text)


def create_event_display() -> LiveEventDisplay | SimpleEventDisplay:
    """Create appropriate event display based on terminal capabilities."""
    if console.is_terminal:
        return LiveEventDisplay()
    return SimpleEventDisplay()


@app.command()
def start(
    foreground: bool = typer.Option(
        False, "--foreground", "-f", help="Run in foreground (don't daemonize)"
    ),
) -> None:
    """Start the Good Night daemon."""
    lifecycle = get_lifecycle()

    if lifecycle.is_running():
        console.print("[yellow]Daemon is already running.[/yellow]")
        raise typer.Exit(1)

    if foreground:
        console.print("[green]Starting Good Night daemon in foreground...[/green]")
        from ..daemon.main import run_daemon

        sys.exit(run_daemon(foreground=True))
    else:
        # Start as background process
        console.print("[green]Starting Good Night daemon...[/green]")

        # Use subprocess to start daemon in background
        python = sys.executable
        module = "good_night.daemon.main"

        subprocess.Popen(
            [python, "-m", module],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait a moment for daemon to start
        import time

        time.sleep(1)

        if lifecycle.is_running():
            console.print(f"[green]Daemon started with PID {lifecycle.get_pid()}[/green]")
        else:
            console.print("[red]Failed to start daemon.[/red]")
            raise typer.Exit(1)


@app.command()
def stop(
    force: bool = typer.Option(
        False, "--force", "-f", help="Force kill the daemon"
    ),
) -> None:
    """Stop the Good Night daemon."""
    lifecycle = get_lifecycle()

    if not lifecycle.is_running():
        console.print("[yellow]Daemon is not running.[/yellow]")
        raise typer.Exit(1)

    pid = lifecycle.get_pid()
    if lifecycle.stop(force=force):
        console.print(f"[green]Daemon (PID {pid}) stopped.[/green]")
    else:
        console.print("[red]Failed to stop daemon.[/red]")
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Show daemon status."""
    lifecycle = get_lifecycle()
    config = load_config()

    table = Table(title="Good Night Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    # Daemon status
    if lifecycle.is_running():
        table.add_row("Status", "[green]Running[/green]")
        table.add_row("PID", str(lifecycle.get_pid()))
    else:
        table.add_row("Status", "[yellow]Stopped[/yellow]")
        table.add_row("PID", "-")

    # Configuration
    table.add_row("Runtime Dir", str(get_runtime_dir()))
    table.add_row("Provider", config.provider.default)
    table.add_row("Dream Interval", f"{config.daemon.dream_interval}s")
    table.add_row("API Enabled", str(config.api.enabled))
    table.add_row("API Port", str(config.api.port))

    console.print(table)


@app.command()
def dream(
    module: Optional[str] = typer.Option(
        None, "--module", "-m", help="Run specific prompt module only"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would be done without executing"
    ),
    connector: Optional[str] = typer.Option(
        None, "--connector", "-c", help="Process specific connector only"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Hide real-time agent events"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Limit to last N conversations (for testing)"
    ),
    days: Optional[int] = typer.Option(
        None, "--days", "-d", help="Days to look back (for first run)"
    ),
) -> None:
    """Trigger a dreaming cycle manually."""
    from ..dreaming.orchestrator import DreamingOrchestrator
    from ..storage.state import StateManager

    config = load_config()
    runtime_dir = get_runtime_dir()

    # Check if this is first run and days not specified
    state_manager = StateManager(runtime_dir)
    connector_ids = [connector] if connector else config.enabled.connectors

    is_first_run = False
    for conn_id in connector_ids:
        conn_state = state_manager.get_connector_state(conn_id)
        if conn_state.last_processed is None:
            is_first_run = True
            break

    # If first run and no --days flag, ask interactively
    if is_first_run and days is None and limit is None:
        console.print("[cyan]First run detected. How many days back should I analyze?[/cyan]")
        console.print("  [dim]This determines how much conversation history to process.[/dim]")
        console.print("  [dim]More days = more comprehensive but slower and more expensive.[/dim]")
        console.print()

        days_input = typer.prompt(
            "Days to look back",
            default=str(config.dreaming.initial_lookback_days),
        )
        try:
            days = int(days_input)
        except ValueError:
            days = config.dreaming.initial_lookback_days

    # Update config with days override if specified
    if days is not None:
        config.dreaming.initial_lookback_days = days

    console.print("[cyan]Starting dreaming cycle...[/cyan]")

    if days is not None:
        console.print(f"[dim]Looking back {days} days[/dim]")

    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be made[/yellow]")

    if not quiet:
        console.print()

    async def run_dream() -> None:
        orchestrator = DreamingOrchestrator(
            runtime_dir=runtime_dir,
            config=config,
            dry_run=dry_run,
        )

        if connector:
            orchestrator.set_connector_filter([connector])
        if module:
            orchestrator.set_prompt_filter([module])
        if limit:
            orchestrator.set_conversation_limit(limit)

        # Set up live event display (default on, --quiet to disable)
        event_display: LiveEventDisplay | SimpleEventDisplay | None = None
        if not quiet:
            event_display = create_event_display()
            orchestrator.set_event_callback(event_display.on_event)
            event_display.start()

        try:
            result = await orchestrator.run()
        finally:
            if event_display:
                event_display.stop()

        if not quiet:
            console.print()  # Add space after events

        if result.success:
            if result.no_new_conversations:
                console.print(f"[yellow]No new conversations to analyze.[/yellow]")
                console.print(f"  Duration: {result.duration_seconds:.1f}s")
                return

            console.print(f"[green]Dreaming cycle completed![/green]")
            console.print(f"  Conversations analyzed: {result.conversations_analyzed}")
            console.print(f"  Issues found: {result.issues_found}")
            console.print(f"  Resolutions generated: {result.resolutions_generated}")
            console.print(f"  Duration: {result.duration_seconds:.1f}s")

            # Display token statistics
            stats = result.statistics
            if stats.total_tokens > 0:
                console.print(f"\n[cyan]Token Statistics:[/cyan]")
                console.print(f"  Input tokens:       {stats.input_tokens:,}")
                console.print(f"  Output tokens:      {stats.output_tokens:,}")
                if stats.cache_read_tokens > 0 or stats.cache_write_tokens > 0:
                    console.print(f"  Cache read tokens:  {stats.cache_read_tokens:,}")
                    console.print(f"  Cache write tokens: {stats.cache_write_tokens:,}")
                console.print(f"  [bold]Estimated cost:   ${stats.get_cost_usd():.4f}[/bold]")

            if result.resolution_files:
                console.print(f"\n[cyan]Resolution files:[/cyan]")
                for filepath in result.resolution_files:
                    console.print(f"  {filepath}")
        else:
            console.print(f"[red]Dreaming cycle failed: {result.error}[/red]")

    asyncio.run(run_dream())


@app.command()
def config(
    action: str = typer.Argument(
        "show", help="Action: show, edit, reset"
    ),
) -> None:
    """Manage configuration."""
    runtime_dir = get_runtime_dir()
    config_path = runtime_dir / "config.yaml"

    if action == "show":
        if config_path.exists():
            console.print(config_path.read_text())
        else:
            console.print("[yellow]No configuration file found.[/yellow]")

    elif action == "edit":
        import os

        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(config_path)])

    elif action == "reset":
        from ..daemon.lifecycle import _copy_defaults

        if typer.confirm("Reset configuration to defaults?"):
            # Backup current config
            if config_path.exists():
                backup = config_path.with_suffix(".yaml.bak")
                config_path.rename(backup)
                console.print(f"[yellow]Backed up to {backup}[/yellow]")

            _copy_defaults(runtime_dir)
            console.print("[green]Configuration reset to defaults.[/green]")
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)


@app.command()
def logs(
    follow: bool = typer.Option(
        False, "--follow", "-f", help="Follow log output"
    ),
    lines: int = typer.Option(
        50, "--lines", "-n", help="Number of lines to show"
    ),
) -> None:
    """View daemon logs."""
    lifecycle = get_lifecycle()
    log_file = lifecycle.log_file

    if not log_file.exists():
        console.print("[yellow]No log file found.[/yellow]")
        raise typer.Exit(1)

    if follow:
        subprocess.run(["tail", "-f", str(log_file)])
    else:
        subprocess.run(["tail", f"-{lines}", str(log_file)])


def main() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
