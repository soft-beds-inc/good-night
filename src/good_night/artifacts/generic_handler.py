"""Generic artifact handler that works from markdown definitions."""

import re
import yaml
from pathlib import Path
from typing import Any

from .base import Artifact, ArtifactHandler, ContentSchema


class GenericHandler(ArtifactHandler):
    """
    Generic handler that derives behavior from markdown artifact definitions.

    Supports:
    - claude-md: CLAUDE.md preference files
    - Other simple markdown-based artifacts
    """

    def __init__(self, artifact_id: str, runtime_dir: Path):
        super().__init__(artifact_id, runtime_dir)
        self._content_schema: ContentSchema | None = None
        self._description = ""

    @property
    def artifact_name(self) -> str:
        # Parse from description or use artifact_id
        return self._description or self.artifact_id.replace("-", " ").title()

    def load_definition(self, md_path: Path) -> None:
        """Load and parse the markdown definition."""
        super().load_definition(md_path)

        content = md_path.read_text()
        sections = self._split_sections(content)

        # Parse description
        if "Description" in sections:
            self._description = sections["Description"].strip().split("\n")[0]

        # Parse content schema
        if "Content Schema" in sections:
            self._content_schema = self._parse_content_schema(sections["Content Schema"])

    def _parse_content_schema(self, content: str) -> ContentSchema:
        """Parse Content Schema section from markdown."""
        # Extract YAML from code block
        yaml_match = re.search(r"```ya?ml?\s*\n(.+?)```", content, re.DOTALL)
        if not yaml_match:
            return ContentSchema(
                required_fields={},
                optional_fields={},
                example={},
                hint="",
            )

        try:
            schema_data = yaml.safe_load(yaml_match.group(1))
        except yaml.YAMLError:
            return ContentSchema(
                required_fields={},
                optional_fields={},
                example={},
                hint="",
            )

        # Parse required_fields - can be dict or None
        required = schema_data.get("required_fields", {}) or {}
        if isinstance(required, dict):
            required_fields = required
        else:
            required_fields = {}

        # Parse optional_fields
        optional = schema_data.get("optional_fields", {}) or {}
        if isinstance(optional, dict):
            optional_fields = optional
        else:
            optional_fields = {}

        return ContentSchema(
            required_fields=required_fields,
            optional_fields=optional_fields,
            example=schema_data.get("example", {}),
            hint=schema_data.get("hint", ""),
        )

    def get_content_schema(self) -> ContentSchema:
        """Get content schema from parsed definition."""
        if self._content_schema:
            return self._content_schema

        # Default fallback
        return ContentSchema(
            required_fields={"content": "The content to write"},
            optional_fields={},
            example={"content": "Example content"},
            hint=f"Provide content for {self.artifact_id}",
        )

    def _get_output_path(self, name: str = "") -> Path:
        """Get output path based on settings."""
        if self.settings.output_path:
            path = Path(self.settings.output_path).expanduser()
            # If output_path ends with .md, it's a file path
            if path.suffix == ".md":
                return path
            # Otherwise it's a directory, append name
            if name:
                return path / f"{name}.md"
            return path

        # Defaults based on artifact type
        if self.artifact_id == "claude-md":
            return Path("CLAUDE.md")

        return Path(f"{self.artifact_id}.md")

    def _generate_claude_md_content(self, content: dict[str, Any]) -> str:
        """Generate CLAUDE.md format content."""
        lines = ["# Project Preferences", ""]

        # Handle preferences list
        if "preferences" in content:
            sections: dict[str, list[str]] = {"General": []}

            for pref in content["preferences"]:
                if isinstance(pref, dict):
                    section = pref.get("section", "General")
                    items = pref.get("items", [])
                    if section not in sections:
                        sections[section] = []
                    sections[section].extend(items)
                elif isinstance(pref, str):
                    sections["General"].append(pref)

            # Write sections
            for section, items in sections.items():
                if items:
                    lines.append(f"## {section}")
                    for item in items:
                        lines.append(f"- {item}")
                    lines.append("")

        # Handle section-based content
        for key, value in content.items():
            if key in ("preferences", "name", "description"):
                continue

            section_name = key.replace("_", " ").title()
            lines.append(f"## {section_name}")

            if isinstance(value, list):
                for item in value:
                    lines.append(f"- {item}")
            elif isinstance(value, str):
                lines.append(value)

            lines.append("")

        return "\n".join(lines).strip() + "\n"

    def _parse_existing_sections(self, content: str) -> dict[str, list[str]]:
        """Parse existing CLAUDE.md into sections."""
        sections: dict[str, list[str]] = {}
        current_section = "General"
        current_items: list[str] = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_items:
                    sections[current_section] = current_items
                current_section = line[3:].strip()
                current_items = []
            elif line.strip():
                current_items.append(line)

        if current_items:
            sections[current_section] = current_items

        return sections

    def _merge_sections(
        self, existing: dict[str, list[str]], new_content: dict[str, Any]
    ) -> str:
        """Merge new content into existing sections."""
        new_sections: dict[str, list[str]] = {}

        if "preferences" in new_content:
            for pref in new_content["preferences"]:
                if isinstance(pref, dict):
                    section = pref.get("section", "General")
                    items = pref.get("items", [])
                    if section not in new_sections:
                        new_sections[section] = []
                    new_sections[section].extend(f"- {item}" for item in items)
                elif isinstance(pref, str):
                    if "General" not in new_sections:
                        new_sections["General"] = []
                    new_sections["General"].append(f"- {pref}")

        for key, value in new_content.items():
            if key in ("preferences", "name", "description"):
                continue
            section_name = key.replace("_", " ").title()
            if section_name not in new_sections:
                new_sections[section_name] = []
            if isinstance(value, list):
                new_sections[section_name].extend(f"- {item}" for item in value)
            elif isinstance(value, str):
                new_sections[section_name].append(value)

        # Merge without duplicates
        merged = dict(existing)
        for section, items in new_sections.items():
            if section in merged:
                existing_set = set(merged[section])
                for item in items:
                    if item not in existing_set:
                        merged[section].append(item)
            else:
                merged[section] = items

        # Rebuild content
        lines = ["# Project Preferences", ""]
        for section, items in merged.items():
            if section != "General" or items:
                lines.append(f"## {section}")
                lines.extend(items)
                lines.append("")

        return "\n".join(lines).strip() + "\n"

    async def create(self, name: str, content: dict[str, Any]) -> Artifact:
        """Create a new artifact."""
        output_path = self._get_output_path(name)

        # Generate content based on artifact type
        if self.artifact_id in ("claude-md", "preferences"):
            md_content = self._generate_claude_md_content(content)
        else:
            # Generic markdown generation
            md_content = self._generate_generic_content(name, content)

        # Write file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_content)

        artifact = Artifact(
            name=name or self.artifact_id,
            path=output_path,
            content=md_content,
            metadata={"operation": "create"},
        )

        # Validate
        is_valid, errors = await self.validate(artifact)
        if not is_valid:
            artifact.metadata["validation_errors"] = errors

        return artifact

    def _generate_generic_content(self, name: str, content: dict[str, Any]) -> str:
        """Generate generic markdown content."""
        lines = [f"# {name}", ""]

        for key, value in content.items():
            if key in ("name",):
                continue

            section_name = key.replace("_", " ").title()
            lines.append(f"## {section_name}")

            if isinstance(value, list):
                for item in value:
                    lines.append(f"- {item}")
            elif isinstance(value, str):
                lines.append(value)
            else:
                lines.append(str(value))

            lines.append("")

        return "\n".join(lines).strip() + "\n"

    async def update(self, path: Path, content: dict[str, Any]) -> Artifact:
        """Update an existing artifact."""
        if not path.exists():
            return await self.create(path.stem, content)

        existing_text = path.read_text()

        if self.artifact_id in ("claude-md", "preferences"):
            existing_sections = self._parse_existing_sections(existing_text)
            new_content = self._merge_sections(existing_sections, content)
        else:
            # For other types, replace entirely
            new_content = self._generate_generic_content(path.stem, content)

        path.write_text(new_content)

        return Artifact(
            name=path.stem,
            path=path,
            content=new_content,
            metadata={"operation": "update", "previous_content": existing_text},
        )

    async def append(self, path: Path, content: dict[str, Any]) -> Artifact:
        """Append content to an existing artifact."""
        if not path.exists():
            return await self.create(path.stem, content)

        existing_text = path.read_text()

        if self.artifact_id in ("claude-md", "preferences"):
            existing_sections = self._parse_existing_sections(existing_text)
            new_content = self._merge_sections(existing_sections, content)
        else:
            # Append to end
            append_content = self._generate_generic_content("", content)
            new_content = existing_text.rstrip() + "\n\n" + append_content

        path.write_text(new_content)

        return Artifact(
            name=path.stem,
            path=path,
            content=new_content,
            metadata={"operation": "append", "previous_content": existing_text},
        )

    async def validate(self, artifact: Artifact) -> tuple[bool, list[str]]:
        """Validate an artifact."""
        errors: list[str] = []
        content = artifact.content

        if not content.strip():
            errors.append(f"{self.artifact_id} is empty")

        if self.artifact_id in ("claude-md", "preferences"):
            # CLAUDE.md specific validation
            if "## " not in content and "# " not in content:
                errors.append("Missing section headers - preferences should be organized")

            line_count = len(content.split("\n"))
            if line_count > 1000:
                errors.append(f"Content too long ({line_count} lines, max 1000)")

            if "- " not in content:
                errors.append("Preferences should be specific and actionable (use list items)")
        else:
            # Generic validation
            line_count = len(content.split("\n"))
            if line_count > 500:
                errors.append(f"Content too long ({line_count} lines, max 500)")

        return len(errors) == 0, errors

    def get_agent_context(self) -> str:
        """Get context for the resolution agent."""
        base_context = super().get_agent_context()

        if self.artifact_id in ("claude-md", "preferences"):
            additional_context = """
## When to Use CLAUDE.md vs Skills

Use CLAUDE.md for PREFERENCES and STYLE:
- "Always use type hints" -> CLAUDE.md
- "Prefer early returns" -> CLAUDE.md
- "Use pytest not unittest" -> CLAUDE.md
- "Follow PEP 8" -> CLAUDE.md

Use Skills for PROCEDURES and TASKS:
- "When deploying, do X then Y then Z" -> Skill
- "To debug, first collect logs, then analyze" -> Skill
- "For code review, check A, B, C in order" -> Skill

Key distinction:
- CLAUDE.md = How Claude should generally behave in this project
- Skills = Step-by-step instructions for specific tasks

When the user gives feedback like:
- "Don't do X" or "Always do Y" -> CLAUDE.md preference
- "When doing X, follow these steps..." -> Skill
"""
            return base_context + additional_context

        return base_context
