"""Processing state management."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ConnectorState:
    """State for a specific connector."""

    last_processed: datetime | None = None
    cursor: str | None = None
    conversations_processed: int = 0
    last_run: datetime | None = None


@dataclass
class DreamingState:
    """State for dreaming runs."""

    last_run: datetime | None = None
    total_runs: int = 0
    last_run_id: str | None = None
    issues_found_total: int = 0
    resolutions_generated_total: int = 0


@dataclass
class ProcessingState:
    """Overall processing state."""

    connectors: dict[str, ConnectorState] = field(default_factory=dict)
    dreaming: DreamingState = field(default_factory=DreamingState)
    version: int = 1


class StateManager:
    """Manages persistent processing state."""

    def __init__(self, runtime_dir: Path):
        self.runtime_dir = runtime_dir
        self.state_file = runtime_dir / "state.json"
        self._state: ProcessingState | None = None

    @property
    def state(self) -> ProcessingState:
        """Get current state, loading from disk if needed."""
        if self._state is None:
            self._state = self._load_state()
        return self._state

    def _load_state(self) -> ProcessingState:
        """Load state from disk."""
        if not self.state_file.exists():
            return ProcessingState()

        try:
            data = json.loads(self.state_file.read_text())
            return self._deserialize_state(data)
        except (json.JSONDecodeError, KeyError):
            return ProcessingState()

    def _deserialize_state(self, data: dict[str, Any]) -> ProcessingState:
        """Deserialize state from JSON data."""
        state = ProcessingState(version=data.get("version", 1))

        # Deserialize connector states
        for conn_id, conn_data in data.get("connectors", {}).items():
            state.connectors[conn_id] = ConnectorState(
                last_processed=self._parse_datetime(conn_data.get("last_processed")),
                cursor=conn_data.get("cursor"),
                conversations_processed=conn_data.get("conversations_processed", 0),
                last_run=self._parse_datetime(conn_data.get("last_run")),
            )

        # Deserialize dreaming state
        dreaming_data = data.get("dreaming", {})
        state.dreaming = DreamingState(
            last_run=self._parse_datetime(dreaming_data.get("last_run")),
            total_runs=dreaming_data.get("total_runs", 0),
            last_run_id=dreaming_data.get("last_run_id"),
            issues_found_total=dreaming_data.get("issues_found_total", 0),
            resolutions_generated_total=dreaming_data.get("resolutions_generated_total", 0),
        )

        return state

    def _parse_datetime(self, value: Any) -> datetime | None:
        """Parse datetime from string or None."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def save(self) -> None:
        """Save state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = self._serialize_state(self.state)
        self.state_file.write_text(json.dumps(data, indent=2))

    def _serialize_state(self, state: ProcessingState) -> dict[str, Any]:
        """Serialize state to JSON-compatible dict."""
        data: dict[str, Any] = {"version": state.version}

        # Serialize connector states
        data["connectors"] = {}
        for conn_id, conn_state in state.connectors.items():
            data["connectors"][conn_id] = {
                "last_processed": (
                    conn_state.last_processed.isoformat()
                    if conn_state.last_processed
                    else None
                ),
                "cursor": conn_state.cursor,
                "conversations_processed": conn_state.conversations_processed,
                "last_run": (
                    conn_state.last_run.isoformat() if conn_state.last_run else None
                ),
            }

        # Serialize dreaming state
        data["dreaming"] = {
            "last_run": (
                state.dreaming.last_run.isoformat() if state.dreaming.last_run else None
            ),
            "total_runs": state.dreaming.total_runs,
            "last_run_id": state.dreaming.last_run_id,
            "issues_found_total": state.dreaming.issues_found_total,
            "resolutions_generated_total": state.dreaming.resolutions_generated_total,
        }

        return data

    def get_connector_state(self, connector_id: str) -> ConnectorState:
        """Get state for a specific connector."""
        if connector_id not in self.state.connectors:
            self.state.connectors[connector_id] = ConnectorState()
        return self.state.connectors[connector_id]

    def update_connector_state(
        self,
        connector_id: str,
        last_processed: datetime | None = None,
        cursor: str | None = None,
        conversations_processed: int | None = None,
    ) -> None:
        """Update state for a connector."""
        conn_state = self.get_connector_state(connector_id)

        if last_processed is not None:
            conn_state.last_processed = last_processed
        if cursor is not None:
            conn_state.cursor = cursor
        if conversations_processed is not None:
            conn_state.conversations_processed += conversations_processed

        conn_state.last_run = datetime.now()
        self.save()

    def update_dreaming_state(
        self,
        run_id: str,
        issues_found: int = 0,
        resolutions_generated: int = 0,
    ) -> None:
        """Update dreaming state after a run."""
        self.state.dreaming.last_run = datetime.now()
        self.state.dreaming.total_runs += 1
        self.state.dreaming.last_run_id = run_id
        self.state.dreaming.issues_found_total += issues_found
        self.state.dreaming.resolutions_generated_total += resolutions_generated
        self.save()
