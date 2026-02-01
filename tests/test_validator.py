"""Tests for resolution validation."""

import pytest

from good_night.linter.validator import ResolutionValidator


class TestResolutionValidator:
    """Tests for ResolutionValidator class."""

    def test_valid_resolution(self) -> None:
        """Test validation of valid resolution."""
        data = {
            "resolutions": [
                {
                    "connector_id": "claude-code",
                    "actions": [
                        {
                            "type": "skill",
                            "target": "~/.claude/skills/test/SKILL.md",
                            "operation": "create",
                            "content": {
                                "name": "test-skill",
                                "description": "Test skill",
                                "instructions": "Do something",
                            },
                            "issue_refs": ["issue-1"],
                            "priority": "medium",
                            "rationale": "Test rationale",
                        }
                    ],
                }
            ]
        }

        validator = ResolutionValidator()
        is_valid, errors = validator.validate(data)

        assert is_valid
        assert len(errors) == 0

    def test_missing_resolutions_field(self) -> None:
        """Test validation fails when resolutions field is missing."""
        data = {}

        validator = ResolutionValidator()
        is_valid, errors = validator.validate(data)

        assert not is_valid
        assert any("resolutions" in e for e in errors)

    def test_missing_connector_id(self) -> None:
        """Test validation fails when connector_id is missing."""
        data = {
            "resolutions": [
                {
                    "actions": []
                }
            ]
        }

        validator = ResolutionValidator()
        is_valid, errors = validator.validate(data)

        assert not is_valid
        assert any("connector_id" in e for e in errors)

    def test_missing_action_fields(self) -> None:
        """Test validation fails when required action fields are missing."""
        data = {
            "resolutions": [
                {
                    "connector_id": "test",
                    "actions": [
                        {
                            "type": "skill",
                            # missing target and operation
                        }
                    ],
                }
            ]
        }

        validator = ResolutionValidator()
        is_valid, errors = validator.validate(data)

        assert not is_valid
        assert any("target" in e for e in errors)
        assert any("operation" in e for e in errors)

    def test_invalid_operation(self) -> None:
        """Test validation fails for invalid operation."""
        data = {
            "resolutions": [
                {
                    "connector_id": "test",
                    "actions": [
                        {
                            "type": "skill",
                            "target": "/path/to/skill",
                            "operation": "invalid_operation",
                        }
                    ],
                }
            ]
        }

        validator = ResolutionValidator()
        is_valid, errors = validator.validate(data)

        assert not is_valid
        assert any("operation" in e for e in errors)

    def test_invalid_priority(self) -> None:
        """Test validation fails for invalid priority."""
        data = {
            "resolutions": [
                {
                    "connector_id": "test",
                    "actions": [
                        {
                            "type": "skill",
                            "target": "/path/to/skill",
                            "operation": "create",
                            "priority": "critical",  # not valid
                        }
                    ],
                }
            ]
        }

        validator = ResolutionValidator()
        is_valid, errors = validator.validate(data)

        assert not is_valid
        assert any("priority" in e for e in errors)

    def test_path_traversal_check(self) -> None:
        """Test validation catches path traversal."""
        data = {
            "resolutions": [
                {
                    "connector_id": "test",
                    "actions": [
                        {
                            "type": "skill",
                            "target": "../../../etc/passwd",
                            "operation": "create",
                        }
                    ],
                }
            ]
        }

        validator = ResolutionValidator()
        is_valid, errors = validator.validate(data)

        assert not is_valid
        assert any("traversal" in e for e in errors)

    def test_skill_content_requirements(self) -> None:
        """Test validation of skill content requirements."""
        data = {
            "resolutions": [
                {
                    "connector_id": "test",
                    "actions": [
                        {
                            "type": "skill",
                            "target": "/path/to/skill",
                            "operation": "create",
                            "content": {},  # missing name and instructions
                        }
                    ],
                }
            ]
        }

        validator = ResolutionValidator()
        is_valid, errors = validator.validate(data)

        assert not is_valid
        assert any("name" in e for e in errors)
