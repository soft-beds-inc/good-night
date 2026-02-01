"""Factory for creating artifact handlers."""

from pathlib import Path

from .base import ArtifactHandler
from .skills_handler import SkillsHandler


class ArtifactHandlerFactory:
    """Factory for creating artifact handlers."""

    _handlers: dict[str, type[ArtifactHandler]] = {
        "claude-skills": SkillsHandler,
        "skill": SkillsHandler,  # Alias
    }

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
        handler = handler_class(runtime_dir)

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
