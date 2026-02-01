"""Step 2 tools for historical comparison."""

import json
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from ...providers.types import ToolDefinition
from ...storage.resolutions import Resolution, ResolutionStorage
from ..report import EnrichedIssue, HistoricalLink
from .base import ToolBuilder


@dataclass
class Step2Context:
    """Context holding state and tool handlers for Step 2 comparison."""

    issues: list[EnrichedIssue]
    resolution_storage: ResolutionStorage
    lookback_days: int = 7
    _issue_index: dict[str, EnrichedIssue] = field(default_factory=dict)
    _resolutions: list[Resolution] | None = None

    def __post_init__(self) -> None:
        """Build issue index."""
        self._issue_index = {i.id: i for i in self.issues}

    def _load_resolutions(self) -> list[Resolution]:
        """Lazy load historical resolutions."""
        if self._resolutions is None:
            self._resolutions = self.resolution_storage.list_recent(limit=self.lookback_days)
        return self._resolutions

    async def get_current_issues(self) -> str:
        """Get all issues from current analysis."""
        result = []
        for issue in self.issues:
            result.append({
                "id": issue.id,
                "type": issue.type.value,
                "severity": issue.severity.value,
                "title": issue.title,
                "description": issue.description[:200] + "..." if len(issue.description) > 200 else issue.description,
                "evidence_count": len(issue.evidence),
                "status": issue.status,
                "is_recurring": issue.is_recurring,
            })

        return json.dumps({
            "issues": result,
            "total": len(result),
        }, indent=2)

    async def get_historical_resolutions(self, limit: int = 7) -> str:
        """Get past resolutions for comparison."""
        resolutions = self._load_resolutions()[:limit]
        result = []

        for res in resolutions:
            actions = []
            for conn_res in res.resolutions:
                for action in conn_res.actions:
                    actions.append({
                        "type": action.type,
                        "target": action.target,
                        "rationale": action.rationale[:100] + "..." if len(action.rationale) > 100 else action.rationale,
                        "issue_refs": action.issue_refs,
                    })

            result.append({
                "id": res.id,
                "created_at": res.created_at.isoformat(),
                "dreaming_run_id": res.dreaming_run_id,
                "actions": actions,
            })

        return json.dumps({
            "resolutions": result,
            "total": len(result),
        }, indent=2)

    async def get_resolution_details(self, resolution_id: str) -> str:
        """Get full details of a specific resolution."""
        resolution = self.resolution_storage.load_by_id(resolution_id)
        if not resolution:
            return json.dumps({"error": f"Resolution {resolution_id} not found"})

        actions = []
        for conn_res in resolution.resolutions:
            for action in conn_res.actions:
                actions.append({
                    "connector_id": conn_res.connector_id,
                    "type": action.type,
                    "target": action.target,
                    "operation": action.operation,
                    "content": action.content,
                    "issue_refs": action.issue_refs,
                    "priority": action.priority,
                    "rationale": action.rationale,
                })

        return json.dumps({
            "id": resolution.id,
            "created_at": resolution.created_at.isoformat(),
            "dreaming_run_id": resolution.dreaming_run_id,
            "actions": actions,
            "metadata": resolution.metadata,
        }, indent=2)

    async def link_issue_to_resolution(
        self,
        issue_id: str,
        resolution_id: str,
        skill_path: str | None = None,
        description: str | None = None,
        relevance_score: float = 0.8,
    ) -> str:
        """Link a current issue to a past resolution."""
        issue = self._issue_index.get(issue_id)
        if not issue:
            return json.dumps({"error": f"Issue {issue_id} not found"})

        # Verify resolution exists
        resolution = self.resolution_storage.load_by_id(resolution_id)
        if not resolution:
            return json.dumps({"error": f"Resolution {resolution_id} not found"})

        # Create link
        link = HistoricalLink(
            resolution_id=resolution_id,
            skill_path=skill_path or "",
            description=description or "",
            relevance_score=relevance_score,
        )

        issue.historical_links.append(link)

        return json.dumps({
            "success": True,
            "message": f"Linked issue '{issue.title}' to resolution {resolution_id[:8]}",
            "link": link.to_dict(),
        })

    async def mark_issue_status(
        self,
        issue_id: str,
        status: str,
    ) -> str:
        """Mark an issue as new, recurring, or already_resolved."""
        issue = self._issue_index.get(issue_id)
        if not issue:
            return json.dumps({"error": f"Issue {issue_id} not found"})

        if status not in ["new", "recurring", "already_resolved"]:
            return json.dumps({"error": f"Invalid status: {status}"})

        issue.status = status
        issue.is_recurring = status == "recurring"

        return json.dumps({
            "success": True,
            "issue_id": issue_id,
            "new_status": status,
            "message": f"Issue '{issue.title}' marked as {status}",
        })

    async def compare_issue_to_resolutions(
        self,
        issue_id: str,
    ) -> str:
        """Find potential matches between an issue and historical resolutions."""
        issue = self._issue_index.get(issue_id)
        if not issue:
            return json.dumps({"error": f"Issue {issue_id} not found"})

        resolutions = self._load_resolutions()
        matches = []

        for res in resolutions:
            for conn_res in res.resolutions:
                for action in conn_res.actions:
                    score = self._calculate_similarity(issue, action)
                    if score > 0.3:  # Minimum threshold
                        matches.append({
                            "resolution_id": res.id,
                            "action_target": action.target,
                            "action_type": action.type,
                            "rationale": action.rationale,
                            "similarity_score": round(score, 2),
                            "issue_refs": action.issue_refs,
                        })

        # Sort by score
        matches.sort(key=lambda x: x["similarity_score"], reverse=True)

        return json.dumps({
            "issue_id": issue_id,
            "issue_title": issue.title,
            "matches": matches[:10],  # Top 10
            "recommendation": self._get_recommendation(matches),
        }, indent=2)

    def _calculate_similarity(self, issue: EnrichedIssue, action: Any) -> float:
        """Calculate similarity score between issue and historical action."""
        scores = []

        # Compare with action content
        if hasattr(action, "content") and action.content:
            content = action.content
            if isinstance(content, dict):
                if "title" in content:
                    title_sim = SequenceMatcher(
                        None, issue.title.lower(), str(content["title"]).lower()
                    ).ratio()
                    scores.append(title_sim * 0.4)

                if "description" in content:
                    desc_sim = SequenceMatcher(
                        None, issue.description.lower()[:500], str(content["description"]).lower()[:500]
                    ).ratio()
                    scores.append(desc_sim * 0.3)

        # Compare with rationale
        if hasattr(action, "rationale") and action.rationale:
            rat_sim = SequenceMatcher(
                None, issue.description.lower()[:300], action.rationale.lower()[:300]
            ).ratio()
            scores.append(rat_sim * 0.3)

        return min(sum(scores), 1.0)

    def _get_recommendation(self, matches: list[dict[str, Any]]) -> str:
        """Get recommendation based on matches."""
        if not matches:
            return "new - No similar historical resolutions found"

        best_score = matches[0]["similarity_score"]
        if best_score > 0.85:
            return "already_resolved - Very similar issue was previously resolved"
        elif best_score > 0.6:
            return "recurring - Similar issue exists but may need updated resolution"
        else:
            return "new - Only weak matches found, consider this a new issue"


def create_step2_tools(context: Step2Context) -> list[ToolDefinition]:
    """Create tool definitions for Step 2 comparison."""
    return [
        ToolBuilder.create(
            name="get_current_issues",
            description="Get all issues from the current analysis that need comparison.",
            handler=context.get_current_issues,
        ),
        ToolBuilder.create(
            name="get_historical_resolutions",
            description="Get recent historical resolutions for comparison.",
            handler=context.get_historical_resolutions,
            properties={
                "limit": {
                    "type": "integer",
                    "description": "Maximum resolutions to return (default: 7)",
                    "default": 7,
                },
            },
        ),
        ToolBuilder.create(
            name="get_resolution_details",
            description="Get full details of a specific resolution including all actions and content.",
            handler=context.get_resolution_details,
            properties={
                "resolution_id": {
                    "type": "string",
                    "description": "ID of the resolution to retrieve",
                },
            },
            required=["resolution_id"],
        ),
        ToolBuilder.create(
            name="compare_issue_to_resolutions",
            description="Automatically compare an issue to all historical resolutions and get similarity scores.",
            handler=context.compare_issue_to_resolutions,
            properties={
                "issue_id": {
                    "type": "string",
                    "description": "ID of the issue to compare",
                },
            },
            required=["issue_id"],
        ),
        ToolBuilder.create(
            name="link_issue_to_resolution",
            description="Link a current issue to a past resolution. Use when you find a relevant historical resolution.",
            handler=context.link_issue_to_resolution,
            properties={
                "issue_id": {
                    "type": "string",
                    "description": "ID of the current issue",
                },
                "resolution_id": {
                    "type": "string",
                    "description": "ID of the historical resolution",
                },
                "skill_path": {
                    "type": "string",
                    "description": "Path to the skill/artifact from the resolution",
                },
                "description": {
                    "type": "string",
                    "description": "Description of how they relate",
                },
                "relevance_score": {
                    "type": "number",
                    "description": "How relevant is this match (0.0-1.0)",
                    "default": 0.8,
                },
            },
            required=["issue_id", "resolution_id"],
        ),
        ToolBuilder.create(
            name="mark_issue_status",
            description="Mark an issue's status based on your analysis of historical matches.",
            handler=context.mark_issue_status,
            properties={
                "issue_id": {
                    "type": "string",
                    "description": "ID of the issue",
                },
                "status": {
                    "type": "string",
                    "enum": ["new", "recurring", "already_resolved"],
                    "description": "new=no prior resolution, recurring=similar issue keeps happening, already_resolved=exact match exists",
                },
            },
            required=["issue_id", "status"],
        ),
    ]
