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


COMPARISON_BASE_PROMPT = """You are comparing current issues with historical resolutions.

Your task is to determine the status of each current issue:
- "new": No similar historical resolution exists
- "recurring": Similar issue was addressed before but keeps happening
- "already_resolved": Exact or very similar issue was already resolved

For each current issue:
1. Use compare_issue_to_resolutions to find potential matches
2. Review match scores and details
3. Link issues to relevant resolutions
4. Mark the issue's status appropriately

Guidelines:
- Similarity score > 0.85 suggests "already_resolved"
- Similarity score 0.6-0.85 suggests "recurring"
- Similarity score < 0.6 suggests "new"
- Consider the rationale and context, not just scores

When marking as recurring:
- Link to the previous resolution
- Note what might need updating

Be systematic: process each issue in order.
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
            summary=f"Comparing {len(enriched.issues)} issues with history",
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

        # Configure agent
        config = AgentConfig(
            model=None,
            system_prompt=COMPARISON_BASE_PROMPT,
            tools=tools,
            max_turns=20,
            temperature=0.5,  # Lower temperature for more consistent comparisons
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

            # Emit completion event
            new_count = len([i for i in context.issues if i.status == "new"])
            recurring_count = len([i for i in context.issues if i.status == "recurring"])
            resolved_count = len([i for i in context.issues if i.status == "already_resolved"])

            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id=agent_id,
                agent_type="comparison",
                event_type="complete",
                summary=f"{new_count} new, {recurring_count} recurring, {resolved_count} resolved",
                details={
                    "new": new_count,
                    "recurring": recurring_count,
                    "resolved": resolved_count,
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

        # Update summary
        new_count = len(enriched.new_issues)
        recurring_count = len(enriched.recurring_issues)
        resolved_count = len(enriched.resolved_issues)

        enriched.summary = (
            f"{new_count} new issues, {recurring_count} recurring, "
            f"{resolved_count} already resolved"
        )

        return enriched

    def _build_initial_prompt(self, issues: list[EnrichedIssue]) -> str:
        """Build the initial prompt for the comparison agent."""
        issue_list = "\n".join([
            f"- {i.id[:8]}: {i.title} ({i.type.value}, {i.severity.value})"
            for i in issues
        ])

        return f"""Compare these {len(issues)} issues with historical resolutions:

{issue_list}

For each issue:
1. Use compare_issue_to_resolutions to find matches
2. If good matches exist (score > 0.6), link them using link_issue_to_resolution
3. Mark status using mark_issue_status (new, recurring, or already_resolved)

Process all issues systematically."""

    async def _compare_non_agentic(self, enriched: EnrichedReport) -> EnrichedReport:
        """Fall back to non-agentic comparison (original implementation)."""
        lookback = self.config.dreaming.historical_lookback
        recent_resolutions = self.storage.list_recent(limit=lookback)

        logger.info(f"Comparing with {len(recent_resolutions)} historical resolutions (non-agentic)")

        enriched.historical_resolutions_checked = len(recent_resolutions)

        # Compare each issue
        for issue in enriched.issues:
            links, status = self._find_historical_matches(issue, recent_resolutions)
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
