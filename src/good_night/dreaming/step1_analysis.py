"""Step 1: Agentic conversation analysis."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from ..config import Config
from ..connectors.base import SourceConnector
from ..connectors.types import Conversation
from ..prompts.handler import PromptHandler
from ..providers.base import AgentProvider
from ..providers.bedrock_provider import AWSAuthenticationError
from ..providers.types import AgentConfig
from .events import AgentEvent, AgentEventStream
from .merger import merge_analysis_reports
from .report import AnalysisReport
from .tools.base import wrap_tool_with_events
from .tools.step1_tools import Step1Context, create_step1_tools

logger = logging.getLogger("good-night.analysis")


ANALYSIS_BASE_PROMPT = """
You are an issue detection agent analyzing AI assistant conversations.

YOUR ROLE: Cast a wide net and detect potential issues. Do NOT filter heavily.
A separate filtering step will decide what's worth acting on.

DETECTION PHILOSOPHY:
================================================================================
Report ANY pattern that MIGHT be worth improving, including:
- Issues that appear across multiple sessions (cross-conversation patterns)
- Issues that appear within a single session (could indicate recurring user frustration)
- Corrections or clarifications that suggest AI misunderstanding
- Style mismatches (verbosity, tone, formatting)
- Capability or knowledge gaps
- User frustrations (even if user doesn't explicitly complain)

WHEN IN DOUBT, REPORT IT. Better to over-detect than miss something important.
The filtering step will decide what's actually worth acting on.
================================================================================

PROJECT CONTEXT AND LOCAL VS GLOBAL ISSUES:
================================================================================
Each conversation has a working_directory that indicates which project it belongs to.
When reporting issues, determine if the issue is:

- local_change=true: Issue is PROJECT-SPECIFIC
  * Related to a specific project's tech stack, architecture, or conventions
  * Examples: "use pytest not unittest for this project", "follow existing naming pattern X"

- local_change=false: Issue is GLOBAL (default)
  * Reflects general user preferences, workflow, or AI behavior patterns
  * Examples: "always run tests before committing", "confirm before destructive actions",
    "user prefers concise responses", "check infrastructure/login before starting"
================================================================================

You have tools to explore conversations - use them to navigate and search efficiently.

Your task:
1. START with scan_recent_human_messages() to quickly see recent user messages across projects
2. Look for ANY patterns: corrections, frustrations, repeated requests, style issues
3. Use search_messages() to find similar patterns
4. Use get_messages() or get_full_message() to get more context where needed
5. Report issues using report_issue tool - include evidence with session_ids and message_indices
6. Set local_change=true for project-specific issues, false for general preferences

Issue types to detect:
- repeated_request: User asks for the same thing (even once if it suggests a pattern)
- frustration_signal: User shows frustration (explicit or implied)
- style_mismatch: AI response style doesn't match what user wants
- capability_gap: AI can't do something user expects
- knowledge_gap: AI lacks knowledge user expects it to have
- other: Any other pattern that might warrant improvement

When reporting issues:
- Include as much evidence as you can find (session_ids and message_indices)
- Quote relevant text to demonstrate the pattern
- Set local_change based on the nature of the issue
- Include a suggested_resolution if you have ideas

Cast a wide net. Report potential issues liberally. Filtering happens later.
"""


class AnalysisStep:
    """Step 1: Analyze conversations from a connector using agentic exploration."""

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
        self.prompt_handler = PromptHandler(runtime_dir / "prompts")
        self.event_stream = event_stream or AgentEventStream()

    async def analyze(
        self,
        connector: SourceConnector,
        conversations: list[Conversation],
        prompt_filter: list[str] | None = None,
    ) -> AnalysisReport:
        """
        Analyze conversations from a connector using agentic exploration.

        Args:
            connector: The source connector
            conversations: Conversations to analyze
            prompt_filter: Only use these prompt modules (None = all enabled)

        Returns:
            AnalysisReport with detected issues
        """
        if not conversations:
            return AnalysisReport(
                connector_id=connector.connector_id,
                conversations_analyzed=0,
                summary="No conversations to analyze",
            )

        # Group conversations by working_directory (project folder)
        folder_groups: dict[str, list[Conversation]] = {}
        for conv in conversations:
            wd = conv.metadata.get("working_directory", "") if conv.metadata else ""
            folder_key = wd or "(no project)"
            if folder_key not in folder_groups:
                folder_groups[folder_key] = []
            folder_groups[folder_key].append(conv)

        # Run one agent per folder in parallel
        reports = await self._run_agents_per_folder(
            connector.connector_id,
            folder_groups,
            prompt_filter,
        )

        # Merge and deduplicate
        merged = merge_analysis_reports(reports)
        merged.connector_id = connector.connector_id
        return merged

    async def _run_agents_per_folder(
        self,
        connector_id: str,
        folder_groups: dict[str, list[Conversation]],
        prompt_filter: list[str] | None,
    ) -> list[AnalysisReport]:
        """Run one agent per project folder in parallel."""
        tasks = []
        for folder_path, convs in folder_groups.items():
            if not convs:
                continue
            # Create a short folder name for agent ID
            folder_name = folder_path.split("/")[-1] if "/" in folder_path else folder_path
            folder_name = folder_name[:20]  # Truncate for readability
            agent_id = f"step1-{connector_id}-{folder_name}"
            tasks.append(self._run_agent(agent_id, convs, prompt_filter, folder_path))

        if not tasks:
            return []

        reports = await asyncio.gather(*tasks)
        return list(reports)

    async def _run_agent(
        self,
        agent_id: str,
        conversations: list[Conversation],
        prompt_filter: list[str] | None,
        folder_path: str | None = None,
    ) -> AnalysisReport:
        """Run a single analysis agent."""
        # Emit start event
        folder_info = f" in {folder_path.split('/')[-1]}" if folder_path else ""
        self.event_stream.emit(AgentEvent(
            timestamp=datetime.now(),
            agent_id=agent_id,
            agent_type="analysis",
            event_type="thinking",
            summary=f"Starting analysis of {len(conversations)} conversations{folder_info}",
        ))

        # Build system prompt from enabled prompts
        system_prompt = self._build_system_prompt(prompt_filter)

        # Create context with conversation data
        context = Step1Context(conversations=conversations)

        # Create tools and wrap with event emission
        tools = create_step1_tools(context)
        tools = [
            wrap_tool_with_events(t, agent_id, "analysis", self.event_stream)
            for t in tools
        ]

        # Configure agent
        config = AgentConfig(
            model=None,  # Use provider default
            system_prompt=system_prompt,
            tools=tools,
            max_turns=30,
            temperature=0.7,
            max_tokens=4096,
        )

        # Build initial prompt with folder context
        initial_prompt = self._build_initial_prompt(conversations, folder_path)

        from ..providers.types import TokenUsage

        token_usage = TokenUsage()

        try:
            # Run agent
            response = await self.provider.run_agent(initial_prompt, config)

            # Extract token usage
            token_usage = response.usage

            # Extract summary from final response
            summary = self._extract_summary(response)

            # Emit completion event
            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id=agent_id,
                agent_type="analysis",
                event_type="complete",
                summary=f"Found {len(context.reported_issues)} issues",
                details={
                    "issues_found": len(context.reported_issues),
                    "tokens": token_usage.total_tokens,
                },
            ))

        except AWSAuthenticationError:
            # Re-raise auth errors to be handled at orchestrator level
            raise

        except Exception as e:
            logger.exception(f"Agent {agent_id} failed: {e}")
            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id=agent_id,
                agent_type="analysis",
                event_type="error",
                summary=f"Analysis failed: {str(e)[:80]}",
            ))
            summary = f"Analysis failed: {e}"

        # Build report from collected issues
        return AnalysisReport(
            connector_id="",  # Will be set by caller
            issues=context.reported_issues,
            conversations_analyzed=len(conversations),
            summary=summary,
            token_usage=token_usage,
        )

    def _build_system_prompt(self, prompt_filter: list[str] | None = None) -> str:
        """Build unified system prompt from all enabled prompts."""
        # Get enabled prompts
        enabled_prompts = prompt_filter or self.config.enabled.prompts

        # Build unified prompt
        return self.prompt_handler.build_unified_system_prompt(
            ANALYSIS_BASE_PROMPT,
            enabled_prompts,
        )

    def _build_initial_prompt(
        self,
        conversations: list[Conversation],
        folder_path: str | None = None,
    ) -> str:
        """Build the initial prompt for the agent."""
        # Calculate some stats for context
        total_messages = sum(len(c.messages) for c in conversations)
        human_messages = sum(len(c.human_messages) for c in conversations)

        folder_context = ""
        if folder_path and folder_path != "(no project)":
            folder_name = folder_path.split("/")[-1]
            folder_context = f"\nProject folder: {folder_name}\nFull path: {folder_path}\n"
            # All conversations are from same folder, so issues are likely local_change=true
            local_hint = "Since all conversations are from the SAME project folder, issues are likely local_change=true (project-specific) unless they reflect general user preferences."
        else:
            local_hint = "Set local_change=true ONLY for project-specific tech/conventions, false for general preferences."

        return f"""Analyze {len(conversations)} conversations for potential issues.
{folder_context}
Conversation Summary:
- Total conversations: {len(conversations)}
- Total messages: {total_messages}
- Human messages: {human_messages}

Your role is DETECTION - cast a wide net and report any potential issues.
A separate filtering step will decide what's worth acting on.

Your task:
1. START with scan_recent_human_messages() to quickly see what users are asking
2. Look for ANY patterns: corrections, frustrations, repeated requests, style issues
3. Use search_messages() to find similar patterns
4. Report issues liberally - better to over-detect than miss something
5. {local_hint}

Report anything that MIGHT be worth improving. When in doubt, report it.

START by calling scan_recent_human_messages() to quickly scan recent user messages."""

    def _extract_summary(self, response) -> str:
        """Extract a summary from the agent's final response."""
        if hasattr(response, "messages") and response.messages:
            # Look for the last assistant message with content
            for msg in reversed(response.messages):
                if msg.role.value == "assistant" and msg.content:
                    # Take first 200 chars as summary
                    content = msg.content.strip()
                    if len(content) > 200:
                        return content[:197] + "..."
                    return content
        return "Analysis completed"
