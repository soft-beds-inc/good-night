"""Step 3 tools for resolution/artifact creation."""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...artifacts.factory import ArtifactHandlerFactory
from ...providers.types import ToolDefinition
from ...storage.resolutions import ConnectorResolution, ConversationReference, Resolution, ResolutionAction
from ..report import EnrichedReport
from .base import ToolBuilder


@dataclass
class ResolutionActionDraft:
    """Draft of a resolution action before finalization."""

    id: str
    artifact_type: str
    name: str
    target_path: str
    operation: str
    content: dict[str, Any]
    issue_refs: list[str]
    references: list[ConversationReference]  # Conversation context for traceability
    rationale: str
    priority: str = "medium"


@dataclass
class Step3Context:
    """Context holding state and tool handlers for Step 3 resolution."""

    report: EnrichedReport
    artifacts_dir: Path
    output_dir: Path
    enabled_artifacts: list[str]
    dry_run: bool = False
    resolution_actions: list[ResolutionActionDraft] = field(default_factory=list)
    _finalized: bool = False

    async def get_issues_to_resolve(self) -> str:
        """Get new and recurring issues that need resolution."""
        issues_to_resolve = self.report.new_issues + self.report.recurring_issues

        result = []
        for issue in issues_to_resolve:
            historical_context = []
            for link in issue.historical_links[:3]:
                historical_context.append({
                    "resolution_id": link.resolution_id,
                    "skill_path": link.skill_path,
                    "relevance_score": link.relevance_score,
                })

            # Extract conversation references from evidence
            conversation_refs = []
            seen_sessions: set[str] = set()
            for evidence in issue.evidence:
                if evidence.session_id and evidence.session_id not in seen_sessions:
                    seen_sessions.add(evidence.session_id)
                    conversation_refs.append({
                        "session_id": evidence.session_id,
                        "working_directory": evidence.working_directory,
                    })

            result.append({
                "id": issue.id,
                "type": issue.type.value,
                "severity": issue.severity.value,
                "title": issue.title,
                "description": issue.description,
                "status": issue.status,
                "is_recurring": issue.is_recurring,
                "suggested_resolution": issue.suggested_resolution,
                "evidence_count": len(issue.evidence),
                "conversation_refs": conversation_refs,
                "historical_context": historical_context,
            })

        return json.dumps({
            "issues": result,
            "total": len(result),
            "new_count": len(self.report.new_issues),
            "recurring_count": len(self.report.recurring_issues),
        }, indent=2)

    async def get_artifact_types(self) -> str:
        """Get available artifact types and their schemas."""
        result = []

        for artifact_id in self.enabled_artifacts:
            try:
                handler = ArtifactHandlerFactory.create(artifact_id, self.artifacts_dir.parent)
                context = handler.get_agent_context()

                result.append({
                    "id": artifact_id,
                    "name": handler.artifact_name,
                    "context": context,
                })
            except Exception as e:
                result.append({
                    "id": artifact_id,
                    "name": artifact_id,
                    "error": str(e),
                })

        return json.dumps({
            "artifact_types": result,
            "total": len(result),
        }, indent=2)

    async def create_resolution_action(
        self,
        artifact_type: str = "",
        name: str = "",
        content: dict[str, Any] | None = None,
        issue_refs: list[str] | None = None,
        target_path: str | None = None,
        operation: str = "create",
        rationale: str = "",
        priority: str = "medium",
    ) -> str:
        """Create a resolution action (skill, guideline, etc)."""
        # Validate required fields
        if not artifact_type:
            return json.dumps({"error": "artifact_type is required"})
        if not name:
            return json.dumps({"error": "name is required"})
        if not content:
            return json.dumps({
                "error": "content is required",
                "hint": self._get_content_hint(artifact_type),
            })
        if not issue_refs:
            return json.dumps({"error": "issue_refs is required (list of issue IDs)"})

        if self._finalized:
            return json.dumps({"error": "Resolution already finalized, cannot add more actions"})

        # Validate artifact type
        if artifact_type not in self.enabled_artifacts:
            return json.dumps({
                "error": f"Artifact type '{artifact_type}' not enabled",
                "enabled_types": self.enabled_artifacts,
            })

        # Generate target path if not provided
        if not target_path:
            target_path = self._generate_target_path(artifact_type, name)

        # Validate operation
        if operation not in ["create", "update", "append"]:
            return json.dumps({"error": f"Invalid operation: {operation}"})

        # Extract conversation references from issue evidence
        references: list[ConversationReference] = []
        seen_sessions: set[str] = set()
        all_issues = self.report.new_issues + self.report.recurring_issues
        for issue in all_issues:
            if issue.id in issue_refs:
                for evidence in issue.evidence:
                    if evidence.session_id and evidence.session_id not in seen_sessions:
                        seen_sessions.add(evidence.session_id)
                        references.append(ConversationReference(
                            session_id=evidence.session_id,
                            working_directory=evidence.working_directory,
                        ))

        # Create draft action
        action = ResolutionActionDraft(
            id=str(uuid.uuid4())[:8],
            artifact_type=artifact_type,
            name=name,
            target_path=target_path,
            operation=operation,
            content=content,
            issue_refs=issue_refs,
            references=references,
            rationale=rationale,
            priority=priority,
        )

        self.resolution_actions.append(action)

        return json.dumps({
            "success": True,
            "action_id": action.id,
            "message": f"Created {operation} action for {artifact_type}: {name}",
            "target_path": target_path,
            "total_actions": len(self.resolution_actions),
        })

    async def list_pending_actions(self) -> str:
        """List all pending resolution actions before finalization."""
        result = []
        for action in self.resolution_actions:
            result.append({
                "id": action.id,
                "artifact_type": action.artifact_type,
                "name": action.name,
                "target_path": action.target_path,
                "operation": action.operation,
                "issue_refs": action.issue_refs,
                "references": [r.to_dict() for r in action.references],
                "priority": action.priority,
                "rationale": action.rationale[:100] + "..." if len(action.rationale) > 100 else action.rationale,
            })

        return json.dumps({
            "pending_actions": result,
            "total": len(result),
            "finalized": self._finalized,
        }, indent=2)

    async def remove_action(self, action_id: str) -> str:
        """Remove a pending action before finalization."""
        if self._finalized:
            return json.dumps({"error": "Resolution already finalized"})

        for i, action in enumerate(self.resolution_actions):
            if action.id == action_id:
                removed = self.resolution_actions.pop(i)
                return json.dumps({
                    "success": True,
                    "message": f"Removed action: {removed.name}",
                    "remaining_actions": len(self.resolution_actions),
                })

        return json.dumps({"error": f"Action {action_id} not found"})

    async def finalize_resolution(self) -> str:
        """Finalize and validate the resolution."""
        if self._finalized:
            return json.dumps({"error": "Resolution already finalized"})

        if not self.resolution_actions:
            return json.dumps({
                "success": False,
                "message": "No actions to finalize",
            })

        # Validate all actions
        errors = []
        for action in self.resolution_actions:
            validation_errors = self._validate_action(action)
            if validation_errors:
                errors.extend(validation_errors)

        if errors:
            return json.dumps({
                "success": False,
                "message": "Validation failed",
                "errors": errors,
            })

        self._finalized = True

        return json.dumps({
            "success": True,
            "message": f"Resolution finalized with {len(self.resolution_actions)} actions",
            "dry_run": self.dry_run,
            "actions_summary": [
                {
                    "type": a.artifact_type,
                    "name": a.name,
                    "operation": a.operation,
                    "target": a.target_path,
                }
                for a in self.resolution_actions
            ],
        })

    def _generate_target_path(self, artifact_type: str, name: str) -> str:
        """Generate target path for an artifact."""
        # Normalize name
        normalized = name.lower().replace(" ", "-").replace("_", "-")

        if artifact_type in ("skill", "claude-skills"):
            return f"~/.claude/skills/{normalized}/SKILL.md"
        elif artifact_type == "guideline":
            return f"~/.good-night/guidelines/{normalized}.md"
        else:
            return f"~/.good-night/artifacts/{artifact_type}/{normalized}"

    def _get_content_hint(self, artifact_type: str) -> str:
        """Get a hint about the required content structure for an artifact type."""
        if artifact_type in ("skill", "claude-skills"):
            return (
                "For skills/claude-skills, content must be an object with: "
                "name (string), description (string), instructions (string). "
                "Optional: when_to_use (string), examples (string). "
                "Example: {\"name\": \"my-skill\", \"description\": \"What it does\", "
                "\"instructions\": \"Detailed instructions for the AI\"}"
            )
        elif artifact_type == "guideline":
            return (
                "For guidelines, content must be an object with: "
                "title (string), content (string). "
                "Example: {\"title\": \"My Guideline\", \"content\": \"Guideline content...\"}"
            )
        return "content must be an object with the artifact's required fields"

    def _validate_action(self, action: ResolutionActionDraft) -> list[str]:
        """Validate a single action."""
        errors = []

        if not action.name:
            errors.append(f"Action {action.id}: name is required")

        if not action.content:
            errors.append(f"Action {action.id}: content is required - {self._get_content_hint(action.artifact_type)}")

        if not action.issue_refs:
            errors.append(f"Action {action.id}: at least one issue_ref is required")

        # Validate content based on artifact type (both "skill" and "claude-skills" use same handler)
        if action.artifact_type in ("skill", "claude-skills"):
            required_fields = ["name", "description", "instructions"]
            for field in required_fields:
                if field not in action.content:
                    errors.append(f"Action {action.id}: skill content missing '{field}'")

        return errors

    def get_resolution(self) -> Resolution | None:
        """Get the finalized resolution object."""
        if not self._finalized or not self.resolution_actions:
            return None

        actions = [
            ResolutionAction(
                type=a.artifact_type,
                target=a.target_path,
                operation=a.operation,
                content=a.content,
                issue_refs=a.issue_refs,
                references=a.references,
                priority=a.priority,
                rationale=a.rationale,
            )
            for a in self.resolution_actions
        ]

        return Resolution(
            id=str(uuid.uuid4()),
            created_at=__import__("datetime").datetime.now(),
            dreaming_run_id="",  # Will be set by caller
            resolutions=[
                ConnectorResolution(
                    connector_id=self.report.connector_id,
                    actions=actions,
                )
            ],
        )


def create_step3_tools(context: Step3Context) -> list[ToolDefinition]:
    """Create tool definitions for Step 3 resolution."""
    return [
        ToolBuilder.create(
            name="get_issues_to_resolve",
            description="Get new and recurring issues that need resolution. Returns issues with their context and any historical links.",
            handler=context.get_issues_to_resolve,
        ),
        ToolBuilder.create(
            name="get_artifact_types",
            description="Get available artifact types and their schemas/formats. Use this to understand what artifacts you can create.",
            handler=context.get_artifact_types,
        ),
        ToolBuilder.create(
            name="create_resolution_action",
            description="""Create a resolution action (skill, guideline, etc).

IMPORTANT: The 'content' parameter is REQUIRED and must be an object with specific fields:
- For 'skill' or 'claude-skills': {"name": "...", "description": "...", "instructions": "...", "when_to_use": "..."}
- For 'guideline': {"title": "...", "content": "..."}

Example for skill:
{
  "artifact_type": "claude-skills",
  "name": "confirm-destructive-actions",
  "content": {
    "name": "Confirm Destructive Actions",
    "description": "Always confirm before executing destructive operations",
    "instructions": "Before running any command that deletes, removes, or overwrites data...",
    "when_to_use": "When the user asks to delete files, drop databases, or perform irreversible operations"
  },
  "issue_refs": ["issue-123"]
}""",
            handler=context.create_resolution_action,
            properties={
                "artifact_type": {
                    "type": "string",
                    "description": "Type of artifact: 'claude-skills' (or 'skill'), 'guideline'",
                },
                "name": {
                    "type": "string",
                    "description": "Name/identifier of the artifact (e.g., 'confirm-destructive-actions')",
                },
                "content": {
                    "type": "object",
                    "description": "REQUIRED object with artifact-specific fields. For skills: {name: string, description: string, instructions: string, when_to_use?: string, examples?: string}",
                    "properties": {
                        "name": {"type": "string", "description": "Display name of the skill"},
                        "description": {"type": "string", "description": "What this skill does"},
                        "instructions": {"type": "string", "description": "Detailed instructions for the AI to follow"},
                        "when_to_use": {"type": "string", "description": "When this skill should be applied"},
                        "examples": {"type": "string", "description": "Optional examples"},
                    },
                    "required": ["name", "description", "instructions"],
                },
                "issue_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "REQUIRED: List of issue IDs this action addresses",
                },
                "target_path": {
                    "type": "string",
                    "description": "Optional: specific path for the artifact (auto-generated if not provided)",
                },
                "operation": {
                    "type": "string",
                    "enum": ["create", "update", "append"],
                    "description": "Operation type (default: create)",
                    "default": "create",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this resolution helps address the issue",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Priority level (default: medium)",
                    "default": "medium",
                },
            },
            required=["artifact_type", "name", "content", "issue_refs"],
        ),
        ToolBuilder.create(
            name="list_pending_actions",
            description="List all pending resolution actions before finalization.",
            handler=context.list_pending_actions,
        ),
        ToolBuilder.create(
            name="remove_action",
            description="Remove a pending action by ID.",
            handler=context.remove_action,
            properties={
                "action_id": {
                    "type": "string",
                    "description": "ID of the action to remove",
                },
            },
            required=["action_id"],
        ),
        ToolBuilder.create(
            name="finalize_resolution",
            description="Finalize and validate the resolution. Call this when all actions are ready.",
            handler=context.finalize_resolution,
        ),
    ]
