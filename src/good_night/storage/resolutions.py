"""Resolution storage management."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ConversationReference:
    """Reference to a conversation for traceability."""

    session_id: str
    working_directory: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "working_directory": self.working_directory,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationReference":
        return cls(
            session_id=data.get("session_id", ""),
            working_directory=data.get("working_directory", ""),
        )


@dataclass
class ResolutionAction:
    """A single resolution action."""

    type: str  # e.g., "skill"
    target: str  # e.g., path to skill file
    operation: str  # create, update, append
    content: dict[str, Any]
    issue_refs: list[str] = field(default_factory=list)
    references: list[ConversationReference] = field(default_factory=list)  # Conversation context
    priority: str = "medium"
    rationale: str = ""
    local_change: bool = False  # True if project-specific, False if global


@dataclass
class ConnectorResolution:
    """Resolutions for a specific connector."""

    connector_id: str
    actions: list[ResolutionAction] = field(default_factory=list)


@dataclass
class Resolution:
    """A complete resolution record."""

    id: str
    created_at: datetime
    dreaming_run_id: str
    resolutions: list[ConnectorResolution] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "metadata": {
                "id": self.id,
                "created_at": self.created_at.isoformat(),
                "dreaming_run_id": self.dreaming_run_id,
                **self.metadata,
            },
            "resolutions": [
                {
                    "connector_id": cr.connector_id,
                    "actions": [
                        {
                            "type": a.type,
                            "target": a.target,
                            "operation": a.operation,
                            "content": a.content,
                            "issue_refs": a.issue_refs,
                            "references": [r.to_dict() for r in a.references],
                            "priority": a.priority,
                            "rationale": a.rationale,
                            "local_change": a.local_change,
                        }
                        for a in cr.actions
                    ],
                }
                for cr in self.resolutions
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Resolution":
        """Create from dictionary."""
        metadata = data.get("metadata", {})
        created_at = metadata.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        resolutions: list[ConnectorResolution] = []
        for res_data in data.get("resolutions", []):
            actions = [
                ResolutionAction(
                    type=a["type"],
                    target=a["target"],
                    operation=a["operation"],
                    content=a.get("content", {}),
                    issue_refs=a.get("issue_refs", []),
                    references=[
                        ConversationReference.from_dict(r)
                        for r in a.get("references", [])
                    ],
                    priority=a.get("priority", "medium"),
                    rationale=a.get("rationale", ""),
                    local_change=a.get("local_change", False),
                )
                for a in res_data.get("actions", [])
            ]
            resolutions.append(
                ConnectorResolution(
                    connector_id=res_data["connector_id"],
                    actions=actions,
                )
            )

        extra_metadata = {k: v for k, v in metadata.items() if k not in ("id", "created_at", "dreaming_run_id")}

        return cls(
            id=metadata.get("id", str(uuid.uuid4())),
            created_at=created_at,
            dreaming_run_id=metadata.get("dreaming_run_id", ""),
            resolutions=resolutions,
            metadata=extra_metadata,
        )


class ResolutionStorage:
    """Manages storage of resolutions."""

    def __init__(self, runtime_dir: Path):
        self.runtime_dir = runtime_dir
        self.resolutions_dir = runtime_dir / "resolutions"
        self.resolutions_dir.mkdir(parents=True, exist_ok=True)

    def _get_filename(self, resolution: Resolution) -> str:
        """Generate filename for a resolution."""
        date_str = resolution.created_at.strftime("%Y-%m-%d")
        short_id = resolution.id[:8]
        return f"{date_str}-{short_id}.json"

    def save(self, resolution: Resolution) -> Path:
        """
        Save a resolution to disk.

        Args:
            resolution: The resolution to save

        Returns:
            Path to the saved file
        """
        filename = self._get_filename(resolution)
        filepath = self.resolutions_dir / filename

        data = resolution.to_dict()
        filepath.write_text(json.dumps(data, indent=2))

        return filepath

    def load(self, filepath: Path) -> Resolution:
        """
        Load a resolution from disk.

        Args:
            filepath: Path to the resolution file

        Returns:
            Resolution object
        """
        data = json.loads(filepath.read_text())
        return Resolution.from_dict(data)

    def load_by_id(self, resolution_id: str) -> Resolution | None:
        """
        Load a resolution by its ID.

        Args:
            resolution_id: The resolution ID

        Returns:
            Resolution if found, None otherwise
        """
        short_id = resolution_id[:8]
        for filepath in self.resolutions_dir.glob(f"*-{short_id}.json"):
            try:
                resolution = self.load(filepath)
                if resolution.id == resolution_id:
                    return resolution
            except (json.JSONDecodeError, KeyError):
                continue
        return None

    def list_recent(self, limit: int = 10) -> list[Resolution]:
        """
        List recent resolutions.

        Args:
            limit: Maximum number of resolutions to return

        Returns:
            List of Resolution objects, newest first
        """
        files = sorted(self.resolutions_dir.glob("*.json"), reverse=True)
        resolutions: list[Resolution] = []

        for filepath in files[:limit]:
            try:
                resolution = self.load(filepath)
                resolutions.append(resolution)
            except (json.JSONDecodeError, KeyError):
                continue

        return resolutions

    def list_by_date_range(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[Resolution]:
        """
        List resolutions within a date range.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            List of Resolution objects
        """
        resolutions: list[Resolution] = []

        for filepath in self.resolutions_dir.glob("*.json"):
            try:
                resolution = self.load(filepath)

                if start_date and resolution.created_at < start_date:
                    continue
                if end_date and resolution.created_at > end_date:
                    continue

                resolutions.append(resolution)
            except (json.JSONDecodeError, KeyError):
                continue

        return sorted(resolutions, key=lambda r: r.created_at, reverse=True)

    def get_actions_for_target(self, target: str) -> list[ResolutionAction]:
        """
        Get all actions that affected a specific target.

        Args:
            target: The target path to search for

        Returns:
            List of ResolutionAction objects
        """
        actions: list[ResolutionAction] = []

        for resolution in self.list_recent(limit=100):
            for conn_res in resolution.resolutions:
                for action in conn_res.actions:
                    if action.target == target:
                        actions.append(action)

        return actions
