"""Base class for source connectors."""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from .types import ConnectorSettings, ConversationBatch


class SourceConnector(ABC):
    """Abstract base class for source connectors."""

    def __init__(self, connector_id: str):
        self.connector_id = connector_id
        self.settings = ConnectorSettings()
        self._definition_loaded = False

    def load_definition(self, md_path: Path) -> None:
        """
        Load connector definition from markdown file.

        Args:
            md_path: Path to the connector markdown definition
        """
        if not md_path.exists():
            raise FileNotFoundError(f"Connector definition not found: {md_path}")

        content = md_path.read_text()
        self.settings = self._parse_definition(content)
        self._definition_loaded = True

    def _parse_definition(self, content: str) -> ConnectorSettings:
        """Parse markdown definition into settings."""
        settings = ConnectorSettings()

        # Parse settings section
        in_settings = False
        for line in content.split("\n"):
            if line.strip().startswith("## Settings"):
                in_settings = True
                continue
            if in_settings and line.strip().startswith("## "):
                break
            if in_settings:
                match = re.match(r"^-\s+(\w+):\s*(.+)$", line)
                if match:
                    key = match.group(1).strip()
                    value = match.group(2).strip()

                    if key == "enabled":
                        settings.enabled = value.lower() == "true"
                    elif key == "path":
                        settings.path = value
                    elif key == "format":
                        settings.format = value
                    else:
                        settings.extra[key] = self._parse_value(value)

        return settings

    def _parse_value(self, value: str) -> Any:
        """Parse a string value into appropriate type."""
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    @property
    @abstractmethod
    def connector_name(self) -> str:
        """Return the name of this connector."""
        ...

    @abstractmethod
    async def extract_conversations(
        self,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> ConversationBatch:
        """
        Extract conversations from the source.

        Args:
            since: Only extract conversations after this timestamp
            cursor: Pagination cursor from previous batch
            limit: Maximum number of conversations to return

        Returns:
            ConversationBatch with extracted conversations
        """
        ...

    @abstractmethod
    async def get_last_processed_timestamp(self) -> datetime | None:
        """Get timestamp of last processed conversation."""
        ...

    @abstractmethod
    async def set_last_processed_timestamp(self, timestamp: datetime) -> None:
        """Set timestamp of last processed conversation."""
        ...
