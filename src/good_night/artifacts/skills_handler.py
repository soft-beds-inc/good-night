"""Claude Skills artifact handler."""

from pathlib import Path
from typing import Any

from .base import Artifact, ArtifactHandler, ContentSchema


class SkillsHandler(ArtifactHandler):
    """Handler for creating Claude Code skill files."""

    def __init__(self, artifact_id: str, runtime_dir: Path):  # noqa: ARG002
        # Always use "claude-skills" as the ID for skills (ignore passed artifact_id)
        super().__init__("claude-skills", runtime_dir)

    @property
    def artifact_name(self) -> str:
        return "Claude Skills"

    def get_content_schema(self) -> ContentSchema:
        """Get the content schema for skills."""
        return ContentSchema(
            required_fields={
                "name": "string - The skill name (used as directory name)",
                "description": "string - What this skill does",
                "instructions": "string - Step-by-step instructions for executing the skill",
            },
            optional_fields={
                "when_to_use": "string - Conditions when this skill should be invoked",
                "examples": "string - Example usages or scenarios",
            },
            example={
                "name": "run-tests",
                "description": "Run the project test suite with coverage",
                "instructions": "1. Activate the virtual environment\n2. Run pytest with coverage flags\n3. Generate coverage report\n4. Report any failures",
                "when_to_use": "When the user asks to run tests or validate changes",
                "examples": "User: 'run the tests'\nUser: 'check if my changes break anything'",
            },
            hint="For skills, content must be an object with 'name', 'description', and 'instructions' as required fields. Skills define reusable, procedural instructions for specific tasks.",
        )

    def _get_output_dir(self) -> Path:
        """Get the output directory for skills."""
        if self.settings.output_path:
            return Path(self.settings.output_path).expanduser()

        if self.settings.scope == "global":
            return Path.home() / ".claude" / "skills"
        else:
            # Project-specific would be relative to current project
            return Path(".claude") / "skills"

    def _generate_skill_content(self, name: str, content: dict[str, Any]) -> str:
        """Generate the skill markdown content."""
        # Build frontmatter
        frontmatter = [
            "---",
            f"name: {content.get('name', name)}",
            f"description: {content.get('description', '')}",
            "version: 1.0.0",
            "generated_by: good-night",
            "---",
        ]

        # Build body
        body_parts = [f"# {content.get('name', name)}"]

        if content.get("description"):
            body_parts.append(f"\n{content['description']}")

        if content.get("when_to_use"):
            body_parts.append("\n## When to Use")
            body_parts.append(content["when_to_use"])

        if content.get("instructions"):
            body_parts.append("\n## Instructions")
            body_parts.append(content["instructions"])

        if content.get("examples"):
            body_parts.append("\n## Examples")
            body_parts.append(content["examples"])

        return "\n".join(frontmatter) + "\n\n" + "\n".join(body_parts)

    async def create(self, name: str, content: dict[str, Any]) -> Artifact:
        """Create a new skill file."""
        output_dir = self._get_output_dir()

        # Create skill directory
        skill_dir = output_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Generate content
        skill_content = self._generate_skill_content(name, content)

        # Write file
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(skill_content)

        artifact = Artifact(
            name=name,
            path=skill_path,
            content=skill_content,
            metadata={"operation": "create"},
        )

        # Validate
        is_valid, errors = await self.validate(artifact)
        if not is_valid:
            artifact.metadata["validation_errors"] = errors

        return artifact

    async def update(self, path: Path, content: dict[str, Any]) -> Artifact:
        """Update an existing skill file."""
        if not path.exists():
            # Create instead
            name = path.parent.name if path.name == "SKILL.md" else path.stem
            return await self.create(name, content)

        # Read existing content
        existing = path.read_text()

        # For now, replace entirely
        # Could be smarter about merging sections
        name = content.get("name", path.parent.name)
        new_content = self._generate_skill_content(name, content)

        path.write_text(new_content)

        return Artifact(
            name=name,
            path=path,
            content=new_content,
            metadata={"operation": "update", "previous_content": existing},
        )

    async def append(self, path: Path, content: dict[str, Any]) -> Artifact:
        """Append content to an existing skill file."""
        if not path.exists():
            return await self.create(path.parent.name, content)

        existing = path.read_text()

        # Append new sections
        new_sections = []

        if content.get("additional_instructions"):
            new_sections.append("\n## Additional Instructions")
            new_sections.append(content["additional_instructions"])

        if content.get("additional_examples"):
            new_sections.append("\n## More Examples")
            new_sections.append(content["additional_examples"])

        if new_sections:
            new_content = existing + "\n" + "\n".join(new_sections)
            path.write_text(new_content)
        else:
            new_content = existing

        return Artifact(
            name=path.parent.name,
            path=path,
            content=new_content,
            metadata={"operation": "append"},
        )

    async def validate(self, artifact: Artifact) -> tuple[bool, list[str]]:
        """Validate a skill artifact."""
        errors: list[str] = []

        content = artifact.content

        # Check for frontmatter
        if not content.startswith("---"):
            errors.append("Missing YAML frontmatter")
        else:
            # Check for required frontmatter fields
            if "name:" not in content:
                errors.append("Missing 'name' in frontmatter")
            if "description:" not in content:
                errors.append("Missing 'description' in frontmatter")

        # Check for required sections
        if "## When to Use" not in content and "## Instructions" not in content:
            errors.append("Missing 'When to Use' or 'Instructions' section")

        # Check line count
        line_count = len(content.split("\n"))
        if line_count > 500:
            errors.append(f"Content too long ({line_count} lines, max 500)")

        return len(errors) == 0, errors
