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
    # Track which issues are included/excluded for resolution
    included_issues: set[str] = field(default_factory=set)
    excluded_issues: dict[str, str] = field(default_factory=dict)  # id -> reason

    def __post_init__(self) -> None:
        """Build issue index."""
        self._issue_index = {i.id: i for i in self.issues}

    def _find_issue(self, issue_id: str) -> EnrichedIssue | None:
        """Find issue by full or partial ID."""
        # Try exact match first
        if issue_id in self._issue_index:
            return self._issue_index[issue_id]
        # Try prefix match for truncated IDs
        for full_id, issue in self._issue_index.items():
            if full_id.startswith(issue_id):
                return issue
        return None

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
        issue = self._find_issue(issue_id)
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
        issue = self._find_issue(issue_id)
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

    async def get_issue_details(self, issue_id: str) -> str:
        """Get full details of an issue including all evidence."""
        issue = self._find_issue(issue_id)
        if not issue:
            return json.dumps({"error": f"Issue {issue_id} not found"})

        return json.dumps({
            "id": issue.id,
            "type": issue.type.value,
            "severity": issue.severity.value,
            "title": issue.title,
            "description": issue.description,
            "evidence": [
                {
                    "session_id": e.session_id,
                    "message_index": e.message_index,
                    "quote": e.quote,
                    "context": e.context,
                    "working_directory": e.working_directory,
                }
                for e in issue.evidence
            ],
            "suggested_resolution": issue.suggested_resolution,
            "local_change": issue.local_change,
            "status": issue.status,
            "is_recurring": issue.is_recurring,
            "historical_links": [h.to_dict() for h in issue.historical_links],
        }, indent=2)

    async def include_issue(
        self,
        issue_id: str,
        rationale: str | None = None,
    ) -> str:
        """
        Include an issue for resolution generation (Step 3).

        Use this when you've determined the issue is worth acting on:
        - It represents a real pattern (cross-conversation or significant single-session)
        - It's not already adequately resolved
        - The potential improvement justifies the effort
        """
        issue = self._find_issue(issue_id)
        if not issue:
            return json.dumps({"error": f"Issue {issue_id} not found"})

        # Remove from excluded if it was there
        if issue.id in self.excluded_issues:
            del self.excluded_issues[issue.id]

        self.included_issues.add(issue.id)

        return json.dumps({
            "success": True,
            "issue_id": issue.id,
            "message": f"Issue '{issue.title}' INCLUDED for resolution",
            "rationale": rationale or "Issue deemed worth resolving",
            "total_included": len(self.included_issues),
        })

    async def exclude_issue(
        self,
        issue_id: str,
        reason: str,
    ) -> str:
        """
        Exclude an issue from resolution generation (Step 3).

        Use this when the issue should NOT be acted on:
        - It's a one-time occurrence (not a pattern)
        - It's already adequately resolved
        - It's normal back-and-forth, not a real issue
        - The evidence is weak or unconvincing
        - The cost of resolution outweighs the benefit
        """
        issue = self._find_issue(issue_id)
        if not issue:
            return json.dumps({"error": f"Issue {issue_id} not found"})

        # Remove from included if it was there
        self.included_issues.discard(issue.id)

        self.excluded_issues[issue.id] = reason

        return json.dumps({
            "success": True,
            "issue_id": issue.id,
            "message": f"Issue '{issue.title}' EXCLUDED from resolution",
            "reason": reason,
            "total_excluded": len(self.excluded_issues),
        })

    async def get_filtering_summary(self) -> str:
        """Get summary of included/excluded issues."""
        included = []
        excluded = []
        pending = []

        for issue in self.issues:
            if issue.id in self.included_issues:
                included.append({
                    "id": issue.id[:8],
                    "title": issue.title,
                    "severity": issue.severity.value,
                })
            elif issue.id in self.excluded_issues:
                excluded.append({
                    "id": issue.id[:8],
                    "title": issue.title,
                    "reason": self.excluded_issues[issue.id],
                })
            else:
                pending.append({
                    "id": issue.id[:8],
                    "title": issue.title,
                    "severity": issue.severity.value,
                })

        return json.dumps({
            "included": included,
            "excluded": excluded,
            "pending": pending,
            "summary": f"{len(included)} included, {len(excluded)} excluded, {len(pending)} pending",
        }, indent=2)

    async def compare_issue_to_resolutions(
        self,
        issue_id: str,
    ) -> str:
        """Find potential matches between an issue and historical resolutions."""
        issue = self._find_issue(issue_id)
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

    async def search_similar_resolutions_vector(
        self,
        issue_id: str,
        min_age_days: int = 7,
        limit: int = 5,
    ) -> str:
        """Search for similar resolutions using vector similarity (Redis).

        This searches older resolutions (7+ days) using semantic similarity,
        finding resolutions that may be conceptually similar even if the
        exact wording differs.
        """
        issue = self._find_issue(issue_id)
        if not issue:
            return json.dumps({"error": f"Issue {issue_id} not found"})

        try:
            from ...storage.redis_vectors import get_vector_store

            store = get_vector_store()

            # Build issue dict for search
            issue_dict = {
                "type": issue.type.value,
                "title": issue.title,
                "description": issue.description,
            }

            # Search for similar resolutions
            results = store.search_by_issue(
                issue=issue_dict,
                k=limit,
                min_age_days=min_age_days,
            )

            if not results:
                return json.dumps({
                    "issue_id": issue_id,
                    "matches": [],
                    "message": "No similar resolutions found in vector store",
                })

            return json.dumps({
                "issue_id": issue_id,
                "issue_title": issue.title,
                "matches": results,
                "recommendation": self._get_vector_recommendation(results),
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Vector search failed: {str(e)}",
                "fallback": "Use compare_issue_to_resolutions for file-based comparison",
            })

    def _get_vector_recommendation(self, matches: list[dict[str, Any]]) -> str:
        """Get recommendation based on vector search matches."""
        if not matches:
            return "new - No similar historical resolutions found in vector store"

        best_score = matches[0].get("score", 0)
        if best_score > 0.85:
            return "already_resolved - Very similar issue was previously resolved (semantic match)"
        elif best_score > 0.6:
            return "recurring - Semantically similar issue exists, may need updated resolution"
        else:
            return "new - Only weak semantic matches found"


def create_step2_tools(context: Step2Context) -> list[ToolDefinition]:
    """Create tool definitions for Step 2 comparison and filtering."""
    return [
        ToolBuilder.create(
            name="get_current_issues",
            description="Get all issues detected in Step 1 that need filtering and comparison.",
            handler=context.get_current_issues,
        ),
        ToolBuilder.create(
            name="get_issue_details",
            description="Get full details of an issue including all evidence. Use to assess issue quality.",
            handler=context.get_issue_details,
            properties={
                "issue_id": {
                    "type": "string",
                    "description": "ID of the issue to retrieve",
                },
            },
            required=["issue_id"],
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
            description="Mark an issue's historical status (new/recurring/already_resolved).",
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
        ToolBuilder.create(
            name="include_issue",
            description="INCLUDE an issue for resolution generation (Step 3). Use when the issue is worth acting on.",
            handler=context.include_issue,
            properties={
                "issue_id": {
                    "type": "string",
                    "description": "ID of the issue to include",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this issue should be resolved",
                },
            },
            required=["issue_id"],
        ),
        ToolBuilder.create(
            name="exclude_issue",
            description="EXCLUDE an issue from resolution generation. Use for noise, one-time issues, or already-resolved problems.",
            handler=context.exclude_issue,
            properties={
                "issue_id": {
                    "type": "string",
                    "description": "ID of the issue to exclude",
                },
                "reason": {
                    "type": "string",
                    "description": "Why this issue should NOT be resolved (e.g., 'one-time occurrence', 'already resolved', 'normal interaction')",
                },
            },
            required=["issue_id", "reason"],
        ),
        ToolBuilder.create(
            name="get_filtering_summary",
            description="Get summary of which issues are included/excluded/pending. Use to check progress.",
            handler=context.get_filtering_summary,
        ),
        ToolBuilder.create(
            name="search_similar_resolutions_vector",
            description="Search for similar historical resolutions using semantic vector similarity. "
                        "Finds resolutions that are conceptually similar even with different wording. "
                        "Searches resolutions older than 7 days by default.",
            handler=context.search_similar_resolutions_vector,
            properties={
                "issue_id": {
                    "type": "string",
                    "description": "ID of the issue to find similar resolutions for",
                },
                "min_age_days": {
                    "type": "integer",
                    "description": "Only search resolutions older than this many days (default: 7)",
                    "default": 7,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of similar resolutions to return (default: 5)",
                    "default": 5,
                },
            },
            required=["issue_id"],
        ),
    ]
