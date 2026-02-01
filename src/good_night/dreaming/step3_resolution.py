"""Step 3: Agentic resolution generation."""

import logging
from datetime import datetime
from pathlib import Path

from ..artifacts.factory import ArtifactHandlerFactory
from ..config import Config
from ..linter.validator import ResolutionValidator
from ..providers.base import AgentProvider
from ..providers.types import AgentConfig
from ..storage.resolutions import Resolution, ResolutionStorage
from .events import AgentEvent, AgentEventStream
from .report import EnrichedReport
from .tools.base import wrap_tool_with_events
from .tools.step3_tools import Step3Context, create_step3_tools

logger = logging.getLogger("good-night.resolution")


RESOLUTION_BASE_PROMPT = """You create resolutions for AI assistant issues.

Resolutions are concrete actions like creating skills or guidelines that will improve the AI's behavior.

Your task:
1. Review issues that need resolution (use get_issues_to_resolve)
2. Understand available artifact types (use get_artifact_types)
3. Create resolution actions for each issue
4. Finalize when all issues are addressed

For each issue, consider:
- What artifact type is most appropriate (skill, guideline, etc.)
- Should this be global or project-specific?
- For recurring issues: should we update existing artifacts?

CRITICAL: When calling create_resolution_action, you MUST provide a 'content' object with required fields:

For skills (artifact_type: "claude-skills" or "skill"):
```json
{
  "artifact_type": "claude-skills",
  "name": "skill-name-here",
  "content": {
    "name": "Human Readable Name",
    "description": "Brief description of what this skill does",
    "instructions": "Detailed step-by-step instructions for the AI to follow",
    "when_to_use": "Conditions when this skill should be applied"
  },
  "issue_refs": ["issue-id-1", "issue-id-2"],
  "rationale": "Why this skill addresses the issue"
}
```

Required content fields for skills:
- name: Display name (e.g., "Confirm Destructive Actions")
- description: What the skill accomplishes
- instructions: Detailed guidance text for the AI

Optional content fields:
- when_to_use: When to apply this skill
- examples: Example scenarios

Guidelines:
- Address high-severity issues first
- Group related issues into single resolutions when appropriate
- Include clear rationale for each action
- Prefer updating existing artifacts for recurring issues
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

        # Create context
        context = Step3Context(
            report=report,
            artifacts_dir=self.runtime_dir / "artifacts",
            output_dir=self.runtime_dir / "output",
            enabled_artifacts=self.config.enabled.artifacts,
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

        # Add artifact type context
        for artifact_id in self.config.enabled.artifacts:
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

For each issue, create appropriate artifacts (skills, guidelines).
Consider grouping related issues if applicable.
"""

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
