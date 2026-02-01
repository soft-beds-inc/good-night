"""Base class for artifact handlers."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..storage.resolutions import ResolutionAction


@dataclass
class ArtifactSettings:
    """Settings parsed from an artifact definition."""

    enabled: bool = True
    output_path: str = ""
    scope: str = "global"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Artifact:
    """An artifact created by a handler."""

    name: str
    path: Path
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ArtifactHandler(ABC):
    """Abstract base class for artifact handlers."""

    def __init__(self, artifact_id: str, runtime_dir: Path):
        self.artifact_id = artifact_id
        self.runtime_dir = runtime_dir
        self.settings = ArtifactSettings()
        self._definition_loaded = False
        self._agent_context = ""
        self._validation_rules: list[str] = []
        self._file_format = ""

    def load_definition(self, md_path: Path) -> None:
        """
        Load artifact definition from markdown file.

        Args:
            md_path: Path to the artifact markdown definition
        """
        if not md_path.exists():
            raise FileNotFoundError(f"Artifact definition not found: {md_path}")

        content = md_path.read_text()
        self._parse_definition(content)
        self._definition_loaded = True

    def _parse_definition(self, content: str) -> None:
        """Parse markdown definition."""
        sections = self._split_sections(content)

        # Parse settings
        if "Settings" in sections:
            self.settings = self._parse_settings(sections["Settings"])

        # Parse validation rules
        if "Validation Rules" in sections:
            self._validation_rules = self._parse_list(sections["Validation Rules"])

        # Parse file format
        if "File Format" in sections:
            self._file_format = sections["File Format"].strip()

        # Parse agent context
        if "For Resolution Agent" in sections:
            self._agent_context = sections["For Resolution Agent"].strip()

    def _split_sections(self, content: str) -> dict[str, str]:
        """Split markdown into sections."""
        sections: dict[str, str] = {}
        current_section = ""
        current_content: list[str] = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line[3:].strip()
                current_content = []
            else:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content)

        return sections

    def _parse_settings(self, content: str) -> ArtifactSettings:
        """Parse settings from markdown list."""
        settings = ArtifactSettings()

        for line in content.split("\n"):
            match = re.match(r"^-\s+(\w+):\s*(.+)$", line)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()

                if key == "enabled":
                    settings.enabled = value.lower() == "true"
                elif key == "output_path":
                    settings.output_path = value
                elif key == "scope":
                    settings.scope = value
                else:
                    settings.extra[key] = self._parse_value(value)

        return settings

    def _parse_list(self, content: str) -> list[str]:
        """Parse markdown list into string list."""
        items: list[str] = []
        for line in content.split("\n"):
            if line.strip().startswith("- "):
                items.append(line.strip()[2:])
        return items

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

    def get_agent_context(self) -> str:
        """
        Get context for the resolution agent.

        Returns:
            String with instructions for generating this artifact type
        """
        if not self._definition_loaded:
            definition_path = self.runtime_dir / "artifacts" / f"{self.artifact_id}.md"
            if definition_path.exists():
                self.load_definition(definition_path)

        context = f"Artifact Type: {self.artifact_id}\n"
        if self._agent_context:
            context += f"\n{self._agent_context}\n"
        if self._file_format:
            context += f"\nFile Format:\n{self._file_format}\n"
        if self._validation_rules:
            context += "\nValidation Rules:\n"
            for rule in self._validation_rules:
                context += f"- {rule}\n"

        return context

    @property
    @abstractmethod
    def artifact_name(self) -> str:
        """Return the name of this artifact type."""
        ...

    @abstractmethod
    async def create(self, name: str, content: dict[str, Any]) -> Artifact:
        """
        Create a new artifact.

        Args:
            name: Name of the artifact
            content: Content dictionary

        Returns:
            Created Artifact
        """
        ...

    @abstractmethod
    async def update(self, path: Path, content: dict[str, Any]) -> Artifact:
        """
        Update an existing artifact.

        Args:
            path: Path to existing artifact
            content: New content

        Returns:
            Updated Artifact
        """
        ...

    @abstractmethod
    async def validate(self, artifact: Artifact) -> tuple[bool, list[str]]:
        """
        Validate an artifact.

        Args:
            artifact: Artifact to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        ...

    async def apply_action(self, action: ResolutionAction) -> Artifact:
        """
        Apply a resolution action.

        Args:
            action: The action to apply

        Returns:
            Created or updated Artifact
        """
        target = Path(action.target).expanduser()

        if action.operation == "create":
            name = target.stem
            artifact = await self.create(name, action.content)
        elif action.operation == "update":
            artifact = await self.update(target, action.content)
        elif action.operation == "append":
            artifact = await self.append(target, action.content)
        else:
            raise ValueError(f"Unknown operation: {action.operation}")

        return artifact

    async def append(self, path: Path, content: dict[str, Any]) -> Artifact:
        """
        Append content to an existing artifact.

        Default implementation updates the artifact.

        Args:
            path: Path to existing artifact
            content: Content to append

        Returns:
            Updated Artifact
        """
        return await self.update(path, content)
