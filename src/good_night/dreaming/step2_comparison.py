"""Step 2: Agentic historical comparison."""

import logging
from datetime import datetime
from pathlib import Path

from ..config import Config
from ..providers.base import AgentProvider
from ..providers.types import AgentConfig
from ..storage.resolutions import ResolutionStorage
from .events import AgentEvent, AgentEventStream
from .report import AnalysisReport, EnrichedIssue, EnrichedReport
from .tools.base import wrap_tool_with_events
from .tools.step2_tools import Step2Context, create_step2_tools

logger = logging.getLogger("good-night.comparison")


COMPARISON_BASE_PROMPT = """You are the FILTERING and COMPARISON agent for the dreaming system.

Step 1 detected potential issues with a wide net. YOUR job is to:
1. FILTER: Decide which issues are worth acting on (include) vs noise (exclude)
2. COMPARE: Check issues against historical resolutions

================================================================================
FILTERING CRITERIA - Be selective! Only INCLUDE issues that:
================================================================================

INCLUDE if:
- Cross-conversation pattern: Issue appears in 2+ different sessions
- Significant single-session issue: Major frustration or capability gap
- Recurring problem: Similar issue was "resolved" before but keeps happening
- Clear improvement opportunity: Resolution would meaningfully help the user

EXCLUDE if:
- One-time occurrence: Normal back-and-forth, user just refining their request
- Already working: Previous resolution is effective, no need to change
- Weak evidence: Not enough examples to justify action
- Minor/cosmetic: Not worth the effort to resolve
- Normal interaction: Standard iterative refinement is expected

================================================================================
HISTORICAL COMPARISON
================================================================================

For issues you're considering including:
- Check if similar issues were previously resolved
- Mark status: "new", "recurring", or "already_resolved"
- Link to relevant historical resolutions

Guidelines for status:
- "already_resolved" (score > 0.85): Very similar issue was resolved → EXCLUDE
- "recurring" (score 0.6-0.85): Issue keeps happening despite resolution → INCLUDE
- "new" (score < 0.6): No prior resolution → INCLUDE if significant

================================================================================
YOUR WORKFLOW
================================================================================

1. Get all issues with get_current_issues()
2. For each issue:
   a. Get full details with get_issue_details()
   b. Assess: Is this a real pattern or noise?
   c. Compare with history using compare_issue_to_resolutions()
   d. Mark status (new/recurring/already_resolved)
   e. DECIDE: include_issue() or exclude_issue()
3. Check progress with get_filtering_summary()

IMPORTANT: Every issue must be either included or excluded. Don't leave issues pending.
Only INCLUDED issues will go to Step 3 for resolution generation.
"""


class ComparisonStep:
    """Step 2: Compare current issues with historical resolutions using agentic approach."""

    def __init__(
        self,
        runtime_dir: Path,
        config: Config,
        provider: AgentProvider | None = None,
        event_stream: AgentEventStream | None = None,
    ):
        self.runtime_dir = runtime_dir
        self.config = config
        self.provider = provider
        self.storage = ResolutionStorage(runtime_dir)
        self.event_stream = event_stream or AgentEventStream()

    async def compare(self, report: AnalysisReport) -> EnrichedReport:
        """
        Compare analysis report with historical resolutions.

        Args:
            report: AnalysisReport from Step 1

        Returns:
            EnrichedReport with historical context
        """
        # Create enriched report with issues converted to EnrichedIssue
        enriched = EnrichedReport.from_analysis_report(report)

        # Check if we have a provider for agentic comparison
        if self.provider is None:
            # Fall back to non-agentic comparison
            return await self._compare_non_agentic(enriched)

        # Check if there are issues to compare
        if not enriched.issues:
            enriched.summary = "No issues to compare"
            return enriched

        # Run agentic comparison
        agent_id = f"step2-{report.connector_id}"

        # Emit start event
        self.event_stream.emit(AgentEvent(
            timestamp=datetime.now(),
            agent_id=agent_id,
            agent_type="comparison",
            event_type="thinking",
            summary=f"Filtering and comparing {len(enriched.issues)} issues",
        ))

        # Create context
        lookback = self.config.dreaming.historical_lookback
        context = Step2Context(
            issues=enriched.issues,
            resolution_storage=self.storage,
            lookback_days=lookback,
        )

        # Create tools with event wrapping
        tools = create_step2_tools(context)
        tools = [
            wrap_tool_with_events(t, agent_id, "comparison", self.event_stream)
            for t in tools
        ]

        # Configure agent - more turns since we're filtering each issue
        config = AgentConfig(
            model=None,
            system_prompt=COMPARISON_BASE_PROMPT,
            tools=tools,
            max_turns=40,  # More turns for filtering + comparison
            temperature=0.5,  # Lower temperature for more consistent decisions
            max_tokens=4096,
        )

        # Build initial prompt
        initial_prompt = self._build_initial_prompt(enriched.issues)

        from ..providers.types import TokenUsage

        step2_usage = TokenUsage()

        try:
            # Run agent
            response = await self.provider.run_agent(initial_prompt, config)

            # Extract token usage
            step2_usage = response.usage

            # Get filtering results
            included_count = len(context.included_issues)
            excluded_count = len(context.excluded_issues)

            # Emit completion event
            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id=agent_id,
                agent_type="comparison",
                event_type="complete",
                summary=f"{included_count} included, {excluded_count} excluded",
                details={
                    "included": included_count,
                    "excluded": excluded_count,
                    "tokens": step2_usage.total_tokens,
                },
            ))

        except Exception as e:
            logger.exception(f"Comparison agent failed: {e}")
            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id=agent_id,
                agent_type="comparison",
                event_type="error",
                summary=f"Comparison failed: {str(e)[:80]}",
            ))
            # Fall back to non-agentic comparison
            return await self._compare_non_agentic(enriched)

        # Update enriched report with comparison results
        enriched.historical_resolutions_checked = lookback

        # Accumulate token usage (step1 + step2)
        enriched.token_usage = enriched.token_usage + step2_usage

        # Filter out excluded issues - only keep included issues for Step 3
        original_count = len(enriched.issues)
        if context.included_issues:
            # Only keep explicitly included issues
            enriched.issues = [
                i for i in enriched.issues
                if i.id in context.included_issues
            ]
        else:
            # If no issues were explicitly included, filter out excluded ones
            enriched.issues = [
                i for i in enriched.issues
                if i.id not in context.excluded_issues
            ]

        # Update summary
        new_count = len(enriched.new_issues)
        recurring_count = len(enriched.recurring_issues)
        excluded_count = original_count - len(enriched.issues)

        enriched.summary = (
            f"{len(enriched.issues)} issues for resolution "
            f"({new_count} new, {recurring_count} recurring), "
            f"{excluded_count} filtered out"
        )

        return enriched

    def _build_initial_prompt(self, issues: list[EnrichedIssue]) -> str:
        """Build the initial prompt for the comparison agent."""
        issue_list = "\n".join([
            f"- {i.id[:8]}: {i.title} ({i.type.value}, {i.severity.value})"
            for i in issues
        ])

        return f"""Filter and compare these {len(issues)} issues from Step 1:

{issue_list}

For EACH issue you must:
1. Get details with get_issue_details()
2. Assess: Is this worth acting on or is it noise?
3. Compare with history using compare_issue_to_resolutions()
4. Mark status (new/recurring/already_resolved)
5. Make a decision: include_issue() or exclude_issue()

Remember:
- Step 1 cast a wide net - many issues may be noise
- Only INCLUDE cross-conversation patterns or significant issues
- EXCLUDE one-time occurrences, normal back-and-forth, already-resolved
- Every issue must be decided (included or excluded)

Start by getting the full issue list, then process each one."""

    async def _compare_non_agentic(self, enriched: EnrichedReport) -> EnrichedReport:
        """Fall back to non-agentic comparison (original implementation)."""
        lookback = self.config.dreaming.historical_lookback
        recent_resolutions = self.storage.list_recent(limit=lookback)

        logger.info(f"Comparing with {len(recent_resolutions)} historical resolutions (non-agentic)")

        enriched.historical_resolutions_checked = len(recent_resolutions)

        # Compare each issue
        for issue in enriched.issues:
            # First check file-based recent resolutions
            links, status = self._find_historical_matches(issue, recent_resolutions)

            # Also search Redis for older resolutions (7+ days)
            redis_matches = await self._search_redis_history(issue)
            if redis_matches:
                links.extend(redis_matches)
                links.sort(key=lambda x: x.relevance_score, reverse=True)
                links = links[:5]  # Keep top 5

                # Update status based on best match
                best_score = links[0].relevance_score if links else 0.0
                if best_score > 0.9:
                    status = "already_resolved"
                elif best_score > 0.7:
                    status = "recurring"

            issue.historical_links = links
            issue.status = status
            issue.is_recurring = status == "recurring"

        # Update summary
        new_count = len(enriched.new_issues)
        recurring_count = len(enriched.recurring_issues)
        resolved_count = len(enriched.resolved_issues)

        enriched.summary = (
            f"{new_count} new issues, {recurring_count} recurring, "
            f"{resolved_count} already resolved"
        )

        return enriched

    async def _search_redis_history(self, issue: EnrichedIssue) -> list:
        """Search Redis vector store for similar historical resolutions."""
        from .report import HistoricalLink

        try:
            from ..storage.redis_vectors import get_vector_store

            store = get_vector_store()

            # Build issue dict for search
            issue_dict = {
                "type": issue.type.value,
                "title": issue.title,
                "description": issue.description,
            }

            # Search for similar resolutions older than 7 days
            results = store.search_by_issue(
                issue=issue_dict,
                k=5,
                min_age_days=7,
            )

            # Convert to HistoricalLink objects
            links = []
            for result in results:
                links.append(HistoricalLink(
                    resolution_id=result["resolution_id"],
                    skill_path=result["target"],
                    description=result["rationale"] or result["description"],
                    relevance_score=result["score"],
                ))

            if links:
                logger.info(f"Found {len(links)} similar resolutions in Redis for issue: {issue.title[:50]}")

            return links

        except Exception as e:
            logger.debug(f"Redis search failed (non-critical): {e}")
            return []

    def _find_historical_matches(
        self,
        issue: EnrichedIssue,
        resolutions: list,
    ) -> tuple[list, str]:
        """Find historical resolutions that match this issue."""
        from .report import HistoricalLink

        links = []
        best_score = 0.0

        for resolution in resolutions:
            for conn_res in resolution.resolutions:
                for action in conn_res.actions:
                    for issue_ref in action.issue_refs:
                        score = self._calculate_relevance(issue, action, issue_ref)

                        if score > 0.5:
                            links.append(HistoricalLink(
                                resolution_id=resolution.id,
                                skill_path=action.target,
                                description=action.rationale,
                                relevance_score=score,
                            ))
                            best_score = max(best_score, score)

        links.sort(key=lambda x: x.relevance_score, reverse=True)

        if not links:
            status = "new"
        elif best_score > 0.9:
            status = "already_resolved"
        elif best_score > 0.7:
            status = "recurring"
        else:
            status = "new"

        return links[:5], status

    def _calculate_relevance(
        self,
        issue: EnrichedIssue,
        action,
        issue_ref: str,
    ) -> float:
        """Calculate relevance score between issue and historical action."""
        from difflib import SequenceMatcher

        scores = []

        if hasattr(action, "content"):
            content = getattr(action, "content", {})

            if "title" in content:
                title_sim = SequenceMatcher(
                    None, issue.title.lower(), str(content["title"]).lower()
                ).ratio()
                scores.append(title_sim * 0.4)

            if "description" in content:
                desc_sim = SequenceMatcher(
                    None, issue.description.lower(), str(content["description"]).lower()
                ).ratio()
                scores.append(desc_sim * 0.3)

        if hasattr(action, "rationale"):
            rationale = getattr(action, "rationale", "")
            rat_sim = SequenceMatcher(
                None, issue.description.lower(), rationale.lower()
            ).ratio()
            scores.append(rat_sim * 0.3)

        if issue.type.value in issue_ref.lower():
            scores.append(0.2)

        return min(sum(scores), 1.0)
