"""Factory for creating source connectors."""

from pathlib import Path

from .base import SourceConnector
from .claude_code import ClaudeCodeConnector


class ConnectorFactory:
    """Factory for creating and managing source connectors."""

    _connectors: dict[str, type[SourceConnector]] = {
        "claude-code": ClaudeCodeConnector,
    }

    @classmethod
    def create(
        cls,
        connector_id: str,
        runtime_dir: Path,
        load_definition: bool = True,
    ) -> SourceConnector:
        """
        Create a connector instance.

        Args:
            connector_id: ID of the connector (e.g., "claude-code")
            runtime_dir: Path to runtime directory
            load_definition: Whether to load the markdown definition

        Returns:
            SourceConnector instance
        """
        if connector_id not in cls._connectors:
            raise ValueError(
                f"Unknown connector: {connector_id}. "
                f"Available: {list(cls._connectors.keys())}"
            )

        connector_class = cls._connectors[connector_id]
        connector = connector_class(runtime_dir)

        if load_definition:
            definition_path = runtime_dir / "connectors" / f"{connector_id}.md"
            if definition_path.exists():
                connector.load_definition(definition_path)

        return connector

    @classmethod
    def create_all(
        cls,
        runtime_dir: Path,
        connector_ids: list[str] | None = None,
    ) -> list[SourceConnector]:
        """
        Create all specified connectors.

        Args:
            runtime_dir: Path to runtime directory
            connector_ids: List of connector IDs to create. If None, creates all.

        Returns:
            List of SourceConnector instances
        """
        if connector_ids is None:
            connector_ids = list(cls._connectors.keys())

        connectors: list[SourceConnector] = []
        for connector_id in connector_ids:
            try:
                connector = cls.create(connector_id, runtime_dir)
                if connector.settings.enabled:
                    connectors.append(connector)
            except Exception:
                # Skip connectors that fail to initialize
                pass

        return connectors

    @classmethod
    def register(cls, connector_id: str, connector_class: type[SourceConnector]) -> None:
        """Register a new connector type."""
        cls._connectors[connector_id] = connector_class

    @classmethod
    def available_connectors(cls) -> list[str]:
        """Return list of available connector IDs."""
        return list(cls._connectors.keys())
