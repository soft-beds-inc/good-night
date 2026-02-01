"""Resolution validation with JSON schema and custom rules."""

import json
from pathlib import Path
from typing import Any


# JSON Schema for resolution format
RESOLUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "metadata": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "created_at": {"type": "string"},
                "dreaming_run_id": {"type": "string"},
            },
        },
        "resolutions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["connector_id", "actions"],
                "properties": {
                    "connector_id": {"type": "string"},
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["type", "target", "operation", "local_change"],
                            "properties": {
                                "type": {"type": "string"},
                                "target": {"type": "string"},
                                "operation": {
                                    "type": "string",
                                    "enum": ["create", "update", "append"],
                                },
                                "content": {"type": "object"},
                                "issue_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                },
                                "rationale": {"type": "string"},
                                "local_change": {"type": "boolean"},
                            },
                        },
                    },
                },
            },
        },
    },
    "required": ["resolutions"],
}


class ResolutionValidator:
    """Validates resolution JSON against schema and custom rules."""

    def __init__(self, schema: dict[str, Any] | None = None):
        self.schema = schema or RESOLUTION_SCHEMA
        self._custom_rules: list[callable] = []

        # Register default custom rules
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Register default validation rules."""
        self._custom_rules.append(self._check_action_targets)
        self._custom_rules.append(self._check_issue_refs)
        self._custom_rules.append(self._check_content_requirements)

    def validate(self, data: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate resolution data.

        Args:
            data: Resolution dictionary to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors: list[str] = []

        # Schema validation
        schema_errors = self._validate_schema(data)
        errors.extend(schema_errors)

        # Custom rules
        for rule in self._custom_rules:
            rule_errors = rule(data)
            errors.extend(rule_errors)

        return len(errors) == 0, errors

    def _validate_schema(self, data: dict[str, Any]) -> list[str]:
        """Validate against JSON schema."""
        errors: list[str] = []

        # Basic structure validation (without jsonschema library)
        if not isinstance(data, dict):
            return ["Resolution must be a dictionary"]

        if "resolutions" not in data:
            errors.append("Missing 'resolutions' field")
            return errors

        if not isinstance(data["resolutions"], list):
            errors.append("'resolutions' must be an array")
            return errors

        for i, res in enumerate(data["resolutions"]):
            prefix = f"resolutions[{i}]"

            if not isinstance(res, dict):
                errors.append(f"{prefix}: must be an object")
                continue

            if "connector_id" not in res:
                errors.append(f"{prefix}: missing 'connector_id'")

            if "actions" not in res:
                errors.append(f"{prefix}: missing 'actions'")
                continue

            if not isinstance(res["actions"], list):
                errors.append(f"{prefix}.actions: must be an array")
                continue

            for j, action in enumerate(res["actions"]):
                action_prefix = f"{prefix}.actions[{j}]"

                if not isinstance(action, dict):
                    errors.append(f"{action_prefix}: must be an object")
                    continue

                for field in ["type", "target", "operation", "local_change"]:
                    if field not in action:
                        errors.append(f"{action_prefix}: missing '{field}'")

                if "operation" in action:
                    valid_ops = ["create", "update", "append"]
                    if action["operation"] not in valid_ops:
                        errors.append(
                            f"{action_prefix}.operation: must be one of {valid_ops}"
                        )

                if "priority" in action:
                    valid_priorities = ["low", "medium", "high"]
                    if action["priority"] not in valid_priorities:
                        errors.append(
                            f"{action_prefix}.priority: must be one of {valid_priorities}"
                        )

                if "local_change" in action:
                    if not isinstance(action["local_change"], bool):
                        errors.append(
                            f"{action_prefix}.local_change: must be a boolean"
                        )

        return errors

    def _check_action_targets(self, data: dict[str, Any]) -> list[str]:
        """Check that action targets are valid paths."""
        errors: list[str] = []

        for i, res in enumerate(data.get("resolutions", [])):
            for j, action in enumerate(res.get("actions", [])):
                target = action.get("target", "")

                if not target:
                    errors.append(
                        f"resolutions[{i}].actions[{j}].target: cannot be empty"
                    )
                    continue

                # Check for suspicious patterns
                if ".." in target:
                    errors.append(
                        f"resolutions[{i}].actions[{j}].target: "
                        "path traversal not allowed"
                    )

                # Check file extension for skill type
                if action.get("type") == "skill":
                    if not target.endswith(".md") and not target.endswith("SKILL.md"):
                        # Allow directory targets that will have SKILL.md added
                        pass

        return errors

    def _check_issue_refs(self, data: dict[str, Any]) -> list[str]:
        """Check that issue references are valid."""
        errors: list[str] = []

        for i, res in enumerate(data.get("resolutions", [])):
            for j, action in enumerate(res.get("actions", [])):
                issue_refs = action.get("issue_refs", [])

                if not isinstance(issue_refs, list):
                    errors.append(
                        f"resolutions[{i}].actions[{j}].issue_refs: must be an array"
                    )
                    continue

                for k, ref in enumerate(issue_refs):
                    if not isinstance(ref, str):
                        errors.append(
                            f"resolutions[{i}].actions[{j}].issue_refs[{k}]: "
                            "must be a string"
                        )

        return errors

    def _check_content_requirements(self, data: dict[str, Any]) -> list[str]:
        """Check that content has required fields based on action type."""
        errors: list[str] = []

        for i, res in enumerate(data.get("resolutions", [])):
            for j, action in enumerate(res.get("actions", [])):
                action_type = action.get("type", "")
                content = action.get("content", {})
                operation = action.get("operation", "create")

                if action_type == "skill" and operation == "create":
                    # Skill create should have name and instructions
                    if not content.get("name"):
                        errors.append(
                            f"resolutions[{i}].actions[{j}].content: "
                            "skill 'create' requires 'name'"
                        )
                    if not content.get("instructions") and not content.get("description"):
                        errors.append(
                            f"resolutions[{i}].actions[{j}].content: "
                            "skill 'create' requires 'instructions' or 'description'"
                        )

        return errors

    def add_custom_rule(self, rule: callable) -> None:
        """Add a custom validation rule."""
        self._custom_rules.append(rule)

    def validate_file(self, filepath: Path) -> tuple[bool, list[str]]:
        """
        Validate a resolution file.

        Args:
            filepath: Path to resolution JSON file

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        try:
            data = json.loads(filepath.read_text())
            return self.validate(data)
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON: {e}"]
        except FileNotFoundError:
            return False, [f"File not found: {filepath}"]
