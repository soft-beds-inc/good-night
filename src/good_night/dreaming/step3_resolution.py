"""Step 3: Agentic resolution generation."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..artifacts.factory import ArtifactHandlerFactory
from ..config import Config
from ..linter.validator import ResolutionValidator
from ..observability import (
    LocalVsGlobalJudge,
    PIISecretDetector,
    ResolutionApplicabilityJudge,
    ResolutionSignificanceJudge,
)
from ..providers.base import AgentProvider
from ..providers.types import AgentConfig
from ..storage.resolutions import Resolution, ResolutionAction, ResolutionStorage
from .events import AgentEvent, AgentEventStream
from .report import EnrichedIssue, EnrichedReport
from .tools.base import wrap_tool_with_events
from .tools.step3_tools import Step3Context, create_step3_tools

logger = logging.getLogger("good-night.resolution")


RESOLUTION_BASE_PROMPT = """You create resolutions for AI assistant issues.

Resolutions are concrete actions (creating or updating artifacts) that will improve the AI's behavior.

## Your Task

1. Review issues that need resolution (use get_issues_to_resolve)
2. Check available artifact types and their schemas (use get_artifact_types)
3. Create resolution actions for each issue (use create_resolution_action)
4. Finalize when all issues are addressed (use finalize_resolution)

## Creating Resolution Actions

Use create_resolution_action with these parameters:
- artifact_type: The type of artifact to create (from get_artifact_types)
- name: Identifier for the artifact (e.g., "confirm-destructive-actions")
- content: Object with fields required by that artifact type (see artifact schemas below)
- issue_refs: List of issue IDs this resolves
- rationale: Brief explanation of why this resolves the issues

IMPORTANT: Each artifact type has its own required content fields. Check the artifact type
documentation below for the specific schema and validation rules.

## Decision Guidelines

For each issue, consider:
- What artifact type is most appropriate for this issue?
- Check the issue's `local_change` field to determine scope:
  * local_change=true → Project-specific artifact (e.g., project CLAUDE.md, .claude/skills/)
  * local_change=false → Global artifact (e.g., ~/.claude/skills/, global settings)
- For recurring issues: should we update an existing artifact instead?

Quality over quantity:
- Address high-severity issues first
- Group related issues into a single resolution when appropriate
- Include clear rationale for each action
- Prefer updating existing artifacts for recurring issues
- Respect local_change: don't create global artifacts for project-specific issues
"""


class ResolutionStep:
    """Step 3: Generate resolutions for detected issues using agentic approach."""

    def __init__(
        self,
        runtime_dir: Path,
        config: Config,
        provider: AgentProvider,
        event_stream: AgentEventStream | None = None,
    ):
        self.runtime_dir = runtime_dir
        self.config = config
        self.provider = provider
        self.validator = ResolutionValidator()
        self.storage = ResolutionStorage(runtime_dir)
        self.event_stream = event_stream or AgentEventStream()

    async def generate(
        self,
        report: EnrichedReport,
        dreaming_run_id: str,
        dry_run: bool = False,
    ) -> tuple[Resolution | None, Path | None]:
        """
        Generate resolutions for the enriched report using agentic approach.

        Args:
            report: EnrichedReport from Step 2
            dreaming_run_id: ID of the current dreaming run
            dry_run: If True, don't save or apply resolutions

        Returns:
            Resolution object if successful, None otherwise
        """
        # Filter to new and recurring issues only
        issues_to_resolve = report.new_issues + report.recurring_issues

        if not issues_to_resolve:
            logger.info("No issues to resolve")
            return None, None

        agent_id = f"step3-{report.connector_id}"

        # Emit start event
        self.event_stream.emit(AgentEvent(
            timestamp=datetime.now(),
            agent_id=agent_id,
            agent_type="resolution",
            event_type="thinking",
            summary=f"Creating resolutions for {len(issues_to_resolve)} issues",
        ))

        # Scan for available artifacts (if .md file exists, it's enabled)
        available_artifacts = ArtifactHandlerFactory.scan_available(self.runtime_dir)

        # Create context
        context = Step3Context(
            report=report,
            artifacts_dir=self.runtime_dir / "artifacts",
            output_dir=self.runtime_dir / "output",
            enabled_artifacts=available_artifacts,
            dry_run=dry_run,
        )

        # Create tools with event wrapping
        tools = create_step3_tools(context)
        tools = [
            wrap_tool_with_events(t, agent_id, "resolution", self.event_stream)
            for t in tools
        ]

        # Build system prompt with artifact context
        system_prompt = self._build_system_prompt()

        # Configure agent
        config = AgentConfig(
            model=None,
            system_prompt=system_prompt,
            tools=tools,
            max_turns=20,
            temperature=0.7,
            max_tokens=4096,
        )

        # Build initial prompt
        initial_prompt = self._build_initial_prompt(issues_to_resolve)

        from ..providers.types import TokenUsage

        step3_usage = TokenUsage()

        try:
            # Run agent
            response = await self.provider.run_agent(initial_prompt, config)

            # Extract token usage
            step3_usage = response.usage

            # Get resolution from context
            resolution = context.get_resolution()

            if resolution:
                resolution.dreaming_run_id = dreaming_run_id

                # Add token usage to metadata
                resolution.metadata["token_usage"] = step3_usage.to_dict()

                # Evaluate resolutions using LLM judges before saving
                try:
                    evaluations = await self._evaluate_all_resolutions(resolution, report)
                    resolution.metadata["evaluations"] = evaluations
                    logger.info(f"Completed LLM judge evaluations for {len(evaluations)} actions")
                except Exception as e:
                    logger.error(f"Failed to evaluate resolutions: {e}")
                    resolution.metadata["evaluations"] = {"error": str(e)}

                # Emit completion event
                action_count = sum(len(cr.actions) for cr in resolution.resolutions)
                self.event_stream.emit(AgentEvent(
                    timestamp=datetime.now(),
                    agent_id=agent_id,
                    agent_type="resolution",
                    event_type="complete",
                    summary=f"Created {action_count} resolution actions",
                    details={
                        "action_count": action_count,
                        "dry_run": dry_run,
                        "tokens": step3_usage.total_tokens,
                    },
                ))

                # Always save the resolution JSON
                filepath = self._save_resolution(resolution, dry_run)
                logger.info(f"Saved resolution to {filepath}")

                if not dry_run:
                    # Store in Redis vector index for future similarity search
                    await self._store_in_redis(resolution)

                    # Apply resolutions (create artifacts)
                    await self._apply_resolutions(resolution)

                return resolution, filepath
            else:
                self.event_stream.emit(AgentEvent(
                    timestamp=datetime.now(),
                    agent_id=agent_id,
                    agent_type="resolution",
                    event_type="complete",
                    summary="No actions finalized",
                ))
                return None, None

        except Exception as e:
            logger.exception(f"Resolution agent failed: {e}")
            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id=agent_id,
                agent_type="resolution",
                event_type="error",
                summary=f"Resolution failed: {str(e)[:80]}",
            ))
            return None, None

    def _build_system_prompt(self) -> str:
        """Build system prompt including artifact module documentation."""
        prompt = RESOLUTION_BASE_PROMPT

        # Add artifact type context (scan for available artifacts)
        available_artifacts = ArtifactHandlerFactory.scan_available(self.runtime_dir)
        for artifact_id in available_artifacts:
            try:
                handler = ArtifactHandlerFactory.create(artifact_id, self.runtime_dir)
                context = handler.get_agent_context()
                prompt += f"\n\n## Artifact Type: {artifact_id}\n{context}"
            except Exception as e:
                logger.warning(f"Failed to load artifact context for {artifact_id}: {e}")

        return prompt

    def _build_initial_prompt(self, issues: list) -> str:
        """Build the initial prompt for the resolution agent."""
        # Sort by severity for prioritization
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_issues = sorted(
            issues,
            key=lambda i: severity_order.get(i.severity.value, 2)
        )

        issue_list = []
        for issue in sorted_issues[:10]:  # Limit to top 10
            issue_list.append(
                f"- [{issue.severity.value.upper()}] {issue.title}\n"
                f"  Type: {issue.type.value}, Status: {issue.status}\n"
                f"  Description: {issue.description[:100]}..."
            )

        return f"""Create resolutions for these {len(issues)} issues:

{chr(10).join(issue_list)}

Steps:
1. Get full issue details with get_issues_to_resolve
2. Check available artifact types with get_artifact_types
3. Create resolution actions using create_resolution_action
4. Review pending actions with list_pending_actions
5. Call finalize_resolution when complete

Consider grouping related issues if they can be addressed by a single artifact.
"""

    async def _evaluate_resolution(
        self,
        action: ResolutionAction,
        issues: list[EnrichedIssue],
    ) -> dict[str, Any]:
        """Evaluate a resolution action using LLM judges.

        Args:
            action: The resolution action to evaluate
            issues: The issues this action addresses

        Returns:
            Dictionary with evaluation results from all judges
        """
        evaluation: dict[str, Any] = {}

        # Prepare content for evaluation
        content_str = json.dumps(action.content) if action.content else ""
        issue_descriptions = "\n".join(i.description for i in issues)
        issue_titles = ", ".join(i.title for i in issues)

        # 1. Check for PII/secrets
        try:
            pii_detector = PIISecretDetector()
            pii_result = pii_detector.score(content=content_str)
            evaluation["pii"] = pii_result

            if pii_result.get("has_pii") and pii_result.get("severity") == "high":
                logger.warning(
                    f"Resolution {action.target} may contain secrets: "
                    f"{pii_result.get('pii_types', [])} - {pii_result.get('explanation', '')}"
                )
        except Exception as e:
            logger.error(f"PII detection failed for {action.target}: {e}")
            evaluation["pii"] = {"error": str(e)}

        # 2. Score significance
        try:
            sig_judge = ResolutionSignificanceJudge()
            sig_result = sig_judge.score(
                resolution_description=action.rationale,
                issue_description=issue_descriptions,
            )
            evaluation["significance"] = sig_result

            if not sig_result.get("is_significant", True):
                logger.info(
                    f"Resolution {action.target} has low significance "
                    f"(score={sig_result.get('significance_score', 0):.2f}): "
                    f"{sig_result.get('rationale', '')}"
                )
        except Exception as e:
            logger.error(f"Significance scoring failed for {action.target}: {e}")
            evaluation["significance"] = {"error": str(e)}

        # 3. Verify applicability
        try:
            app_judge = ResolutionApplicabilityJudge()
            app_result = app_judge.score(
                issue_title=issue_titles,
                issue_description=issue_descriptions,
                resolution_content=action.content,
                resolution_type=action.type,
            )
            evaluation["applicability"] = app_result

            if not app_result.get("is_applicable", True):
                logger.warning(
                    f"Resolution {action.target} may not fully address issues "
                    f"(coverage={app_result.get('coverage_score', 0):.2f}): "
                    f"gaps={app_result.get('gaps', [])}"
                )
        except Exception as e:
            logger.error(f"Applicability check failed for {action.target}: {e}")
            evaluation["applicability"] = {"error": str(e)}

        # 4. Validate local_change flag
        try:
            local_judge = LocalVsGlobalJudge()
            # Get working directory from first issue with evidence
            working_dir = ""
            for issue in issues:
                if issue.evidence:
                    working_dir = issue.evidence[0].working_directory
                    if working_dir:
                        break

            local_result = local_judge.score(
                issue_description=issue_descriptions,
                resolution_description=action.rationale,
                working_directory=working_dir,
            )
            evaluation["local_vs_global"] = local_result

            # Check if local_change flag matches judge recommendation
            expected_local = local_result.get("should_be_local", False)
            if action.local_change != expected_local and local_result.get("confidence", 0) > 0.7:
                logger.warning(
                    f"Resolution {action.target} local_change={action.local_change} "
                    f"but judge recommends should_be_local={expected_local} "
                    f"(confidence={local_result.get('confidence', 0):.2f}): "
                    f"{local_result.get('rationale', '')}"
                )
        except Exception as e:
            logger.error(f"Local vs global check failed for {action.target}: {e}")
            evaluation["local_vs_global"] = {"error": str(e)}

        return evaluation

    async def _evaluate_all_resolutions(
        self,
        resolution: Resolution,
        report: EnrichedReport,
    ) -> dict[str, list[dict[str, Any]]]:
        """Evaluate all resolution actions using LLM judges.

        Args:
            resolution: The Resolution object containing all actions
            report: The EnrichedReport with issues

        Returns:
            Dictionary mapping action targets to their evaluation results
        """
        evaluations: dict[str, list[dict[str, Any]]] = {}

        # Build a map of issue_id to EnrichedIssue for quick lookup
        issues_to_resolve = report.new_issues + report.recurring_issues
        issue_map = {issue.id: issue for issue in issues_to_resolve}

        for conn_res in resolution.resolutions:
            for action in conn_res.actions:
                # Get the issues this action addresses
                addressed_issues = [
                    issue_map[ref]
                    for ref in action.issue_refs
                    if ref in issue_map
                ]

                if not addressed_issues:
                    logger.warning(
                        f"Resolution {action.target} has no matching issues "
                        f"(refs: {action.issue_refs})"
                    )
                    continue

                # Evaluate this action
                eval_result = await self._evaluate_resolution(action, addressed_issues)
                evaluations[action.target] = [eval_result]

                logger.info(
                    f"Evaluated resolution {action.target}: "
                    f"pii={eval_result.get('pii', {}).get('has_pii', False)}, "
                    f"significance={eval_result.get('significance', {}).get('significance_score', 'N/A')}, "
                    f"applicability={eval_result.get('applicability', {}).get('coverage_score', 'N/A')}"
                )

        return evaluations

    def _save_resolution(self, resolution: Resolution, dry_run: bool) -> Path:
        """Save resolution JSON to appropriate location."""
        if dry_run:
            # Save to dry-runs folder
            dry_runs_dir = self.runtime_dir / "dry-runs"
            dry_runs_dir.mkdir(parents=True, exist_ok=True)

            date_str = resolution.created_at.strftime("%Y-%m-%d_%H%M%S")
            short_id = resolution.id[:8]
            filename = f"{date_str}-{short_id}.json"
            filepath = dry_runs_dir / filename

            import json
            data = resolution.to_dict()
            filepath.write_text(json.dumps(data, indent=2))
            return filepath
        else:
            # Save to regular resolutions folder
            return self.storage.save(resolution)

    async def _store_in_redis(self, resolution: Resolution) -> None:
        """Store resolution actions in Redis for vector similarity search."""
        try:
            from ..storage.redis_vectors import get_vector_store

            store = get_vector_store()
            stored_count = 0

            for conn_res in resolution.resolutions:
                for action in conn_res.actions:
                    action_dict = {
                        "type": action.type,
                        "target": action.target,
                        "operation": action.operation,
                        "content": action.content,
                        "rationale": action.rationale,
                        "issue_refs": action.issue_refs,
                        "local_change": action.local_change,
                    }

                    if store.store_resolution(
                        resolution_id=resolution.id,
                        connector_id=conn_res.connector_id,
                        action=action_dict,
                        created_at=resolution.created_at,
                    ):
                        stored_count += 1

            logger.info(f"Stored {stored_count} resolution actions in Redis")

        except Exception as e:
            # Don't fail the resolution if Redis storage fails
            logger.warning(f"Failed to store resolution in Redis: {e}")

    async def _apply_resolutions(self, resolution: Resolution) -> None:
        """Apply resolutions by creating artifacts."""
        for conn_res in resolution.resolutions:
            for action in conn_res.actions:
                try:
                    handler = ArtifactHandlerFactory.create(action.type, self.runtime_dir)
                    await handler.apply_action(action)
                    logger.info(f"Applied action: {action.operation} {action.target}")
                except Exception as e:
                    logger.error(f"Failed to apply action {action.target}: {e}")
