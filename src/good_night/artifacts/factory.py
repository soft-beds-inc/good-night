"""Factory for creating artifact handlers."""

from pathlib import Path

from .base import ArtifactHandler
from .generic_handler import GenericHandler
from .skills_handler import SkillsHandler


class ArtifactHandlerFactory:
    """Factory for creating artifact handlers."""

    _handlers: dict[str, type[ArtifactHandler]] = {
        "claude-skills": SkillsHandler,
        "skill": SkillsHandler,  # Alias
        "claude-md": GenericHandler,
        "preferences": GenericHandler,  # Alias
    }

    @classmethod
    def scan_available(cls, runtime_dir: Path) -> list[str]:
        """
        Scan artifacts directory for available artifact types.

        An artifact is available if its .md definition file exists.

        Args:
            runtime_dir: Path to runtime directory (~/.good-night)

        Returns:
            List of artifact IDs (e.g., ["claude-skills", "claude-md"])
        """
        artifacts_dir = runtime_dir / "artifacts"
        if not artifacts_dir.exists():
            return []

        available = []
        for md_file in artifacts_dir.glob("*.md"):
            artifact_id = md_file.stem  # e.g., "claude-skills" from "claude-skills.md"
            # Only include if we have a handler for it
            if artifact_id in cls._handlers:
                available.append(artifact_id)

        return available

    @classmethod
    def create(cls, artifact_id: str, runtime_dir: Path) -> ArtifactHandler:
        """
        Create an artifact handler.

        Args:
            artifact_id: ID of the artifact type
            runtime_dir: Path to runtime directory

        Returns:
            ArtifactHandler instance
        """
        if artifact_id not in cls._handlers:
            raise ValueError(
                f"Unknown artifact type: {artifact_id}. "
                f"Available: {list(cls._handlers.keys())}"
            )

        handler_class = cls._handlers[artifact_id]
        handler = handler_class(artifact_id, runtime_dir)

        # Load definition if available
        definition_path = runtime_dir / "artifacts" / f"{artifact_id}.md"
        if definition_path.exists():
            handler.load_definition(definition_path)

        return handler

    @classmethod
    def register(cls, artifact_id: str, handler_class: type[ArtifactHandler]) -> None:
        """Register a new artifact handler type."""
        cls._handlers[artifact_id] = handler_class

    @classmethod
    def available_handlers(cls) -> list[str]:
        """Return list of available artifact type IDs."""
        return list(cls._handlers.keys())
