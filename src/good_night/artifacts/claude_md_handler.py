"""CLAUDE.md artifact handler for project-specific preferences."""

import re
from pathlib import Path
from typing import Any

from .base import Artifact, ArtifactHandler


class ClaudeMdHandler(ArtifactHandler):
    """Handler for managing CLAUDE.md preference files."""

    def __init__(self, runtime_dir: Path):
        super().__init__("claude-md", runtime_dir)

    @property
    def artifact_name(self) -> str:
        return "CLAUDE.md Preferences"

    def _get_output_path(self) -> Path:
        """Get the output path for CLAUDE.md."""
        if self.settings.output_path:
            return Path(self.settings.output_path).expanduser()
        # Default to project root CLAUDE.md
        return Path("CLAUDE.md")

    def _parse_existing_sections(self, content: str) -> dict[str, list[str]]:
        """Parse existing CLAUDE.md into sections."""
        sections: dict[str, list[str]] = {}
        current_section = "General"
        current_items: list[str] = []

        for line in content.split("\n"):
            # Match ## headers
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

    def _generate_content(self, content: dict[str, Any]) -> str:
        """Generate CLAUDE.md content from structured input."""
        lines = ["# Project Preferences", ""]

        # Handle direct preferences list
        if "preferences" in content:
            for pref in content["preferences"]:
                if isinstance(pref, dict):
                    section = pref.get("section", "General")
                    items = pref.get("items", [])
                    if items:
                        lines.append(f"## {section}")
                        for item in items:
                            lines.append(f"- {item}")
                        lines.append("")
                elif isinstance(pref, str):
                    lines.append(f"- {pref}")

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

    def _merge_sections(
        self, existing: dict[str, list[str]], new_content: dict[str, Any]
    ) -> str:
        """Merge new content into existing sections."""
        # Parse new content into sections
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

        # Merge: add new items to existing sections, create new sections as needed
        merged = dict(existing)
        for section, items in new_sections.items():
            if section in merged:
                # Add only non-duplicate items
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
        """Create a new CLAUDE.md file."""
        output_path = self._get_output_path()

        # Generate content
        md_content = self._generate_content(content)

        # Write file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_content)

        artifact = Artifact(
            name=name or "CLAUDE.md",
            path=output_path,
            content=md_content,
            metadata={"operation": "create"},
        )

        # Validate
        is_valid, errors = await self.validate(artifact)
        if not is_valid:
            artifact.metadata["validation_errors"] = errors

        return artifact

    async def update(self, path: Path, content: dict[str, Any]) -> Artifact:
        """Update an existing CLAUDE.md file."""
        if not path.exists():
            return await self.create("CLAUDE.md", content)

        # Read existing content
        existing_text = path.read_text()
        existing_sections = self._parse_existing_sections(existing_text)

        # Merge content
        new_content = self._merge_sections(existing_sections, content)

        path.write_text(new_content)

        return Artifact(
            name="CLAUDE.md",
            path=path,
            content=new_content,
            metadata={"operation": "update", "previous_content": existing_text},
        )

    async def append(self, path: Path, content: dict[str, Any]) -> Artifact:
        """Append content to an existing CLAUDE.md file."""
        if not path.exists():
            return await self.create("CLAUDE.md", content)

        existing_text = path.read_text()
        existing_sections = self._parse_existing_sections(existing_text)

        # Merge without overwriting
        new_content = self._merge_sections(existing_sections, content)

        path.write_text(new_content)

        return Artifact(
            name="CLAUDE.md",
            path=path,
            content=new_content,
            metadata={"operation": "append", "previous_content": existing_text},
        )

    async def validate(self, artifact: Artifact) -> tuple[bool, list[str]]:
        """Validate a CLAUDE.md artifact."""
        errors: list[str] = []
        content = artifact.content

        # Check for basic markdown structure
        if not content.strip():
            errors.append("CLAUDE.md is empty")

        # Check for section headers
        if "## " not in content and "# " not in content:
            errors.append("Missing section headers - preferences should be organized")

        # Check line count
        line_count = len(content.split("\n"))
        if line_count > 1000:
            errors.append(f"Content too long ({line_count} lines, max 1000)")

        # Check for actionable preferences (should have list items or clear statements)
        if "- " not in content and not re.search(r"^[A-Z][^.!?]*[.!?]$", content, re.MULTILINE):
            errors.append("Preferences should be specific and actionable (use list items)")

        return len(errors) == 0, errors

    def get_agent_context(self) -> str:
        """
        Get context for the resolution agent about when to use CLAUDE.md vs skills.

        Returns:
            String with instructions for the agent
        """
        base_context = super().get_agent_context()

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
