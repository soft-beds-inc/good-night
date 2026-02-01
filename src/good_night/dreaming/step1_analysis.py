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


ANALYSIS_BASE_PROMPT = """You are analyzing AI assistant conversations to find CROSS-CONVERSATION patterns and issues.

CRITICAL REQUIREMENT - CROSS-CONVERSATION PATTERNS ONLY:
================================================================================
Only report issues that appear ACROSS MULTIPLE CONVERSATIONS (at least 2-3 different sessions).

The user does THOUSANDS of interactions. Single-instance issues are NOT worth reporting.
One-time corrections within a session are NORMAL interaction - ignore them completely.

DO NOT REPORT:
- One-time clarifications or corrections within a single conversation
- Normal back-and-forth where user refines their request in one session
- Any issue that appears in only ONE session
- Standard iterative refinement (this is expected and normal)

ONLY REPORT:
- Issues that appear in 2-3+ DIFFERENT conversation sessions
- Systematic patterns where the same problem recurs across sessions
- Recurring user frustrations about the SAME topic in multiple conversations
- Capability gaps that frustrate the user repeatedly over time
================================================================================

You have tools to explore conversations - use them to navigate and search efficiently.
Report issues ONLY if they span multiple sessions using the report_issue tool.

Your task:
1. Start by listing conversations to see what's available
2. Explore messages systematically, looking for CROSS-SESSION patterns
3. Use search to find recurring issues across different conversations
4. Only report issues that appear in 2+ different sessions with evidence
5. Be highly selective - most single-session issues should be ignored

Issue types to look for (only if they appear across multiple sessions):
- repeated_request: User asks for the same thing in multiple different sessions
- frustration_signal: User shows similar frustration across multiple sessions
- style_mismatch: AI response style consistently mismatches across sessions
- capability_gap: Same capability gap frustrates user in multiple sessions
- knowledge_gap: Same knowledge gap appears in multiple sessions
- other: Any other significant cross-session pattern

When reporting issues:
- MUST include evidence from 2+ different sessions (session_ids and message_indices)
- Quote relevant text from MULTIPLE sessions to prove the pattern
- Clearly state how many sessions are affected
- Prioritize by severity (critical > high > medium > low)

Be highly selective. The threshold for reporting is HIGH - only systematic, recurring issues matter.
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

        # Determine how many agents to use
        num_agents = self.config.dreaming.exploration_agents

        if num_agents == 1:
            # Single agent mode
            report = await self._run_single_agent(
                connector.connector_id,
                conversations,
                prompt_filter,
            )
        else:
            # Multi-agent mode - split conversations
            report = await self._run_parallel_agents(
                connector.connector_id,
                conversations,
                prompt_filter,
                num_agents,
            )

        # Merge and deduplicate
        merged = merge_analysis_reports([report])
        merged.connector_id = connector.connector_id
        return merged

    async def _run_single_agent(
        self,
        connector_id: str,
        conversations: list[Conversation],
        prompt_filter: list[str] | None,
    ) -> AnalysisReport:
        """Run analysis with a single agent."""
        agent_id = f"step1-{connector_id}"
        return await self._run_agent(
            agent_id,
            conversations,
            prompt_filter,
        )

    async def _run_parallel_agents(
        self,
        connector_id: str,
        conversations: list[Conversation],
        prompt_filter: list[str] | None,
        num_agents: int,
    ) -> AnalysisReport:
        """Run analysis with multiple parallel agents."""
        # Split conversations among agents
        chunks = [conversations[i::num_agents] for i in range(num_agents)]

        # Run agents in parallel
        tasks = []
        for i, chunk in enumerate(chunks):
            if chunk:  # Skip empty chunks
                agent_id = f"step1-agent-{i+1}"
                tasks.append(self._run_agent(agent_id, chunk, prompt_filter))

        reports = await asyncio.gather(*tasks)

        # Merge all reports
        merged = merge_analysis_reports(list(reports))
        merged.connector_id = connector_id
        return merged

    async def _run_agent(
        self,
        agent_id: str,
        conversations: list[Conversation],
        prompt_filter: list[str] | None,
    ) -> AnalysisReport:
        """Run a single analysis agent."""
        # Emit start event
        self.event_stream.emit(AgentEvent(
            timestamp=datetime.now(),
            agent_id=agent_id,
            agent_type="analysis",
            event_type="thinking",
            summary=f"Starting analysis of {len(conversations)} conversations",
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

        # Build initial prompt
        initial_prompt = self._build_initial_prompt(conversations)

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

    def _build_initial_prompt(self, conversations: list[Conversation]) -> str:
        """Build the initial prompt for the agent."""
        # Calculate some stats for context
        total_messages = sum(len(c.messages) for c in conversations)
        human_messages = sum(len(c.human_messages) for c in conversations)

        return f"""Analyze {len(conversations)} conversations for CROSS-CONVERSATION patterns.

Conversation Summary:
- Total conversations: {len(conversations)}
- Total messages: {total_messages}
- Human messages: {human_messages}

CRITICAL: Only report issues that appear in 2-3+ DIFFERENT sessions.
Single-session issues are NOT worth reporting - the user does thousands of interactions.
One-time corrections are NORMAL - ignore them completely.

Your task:
1. List conversations to see what's available
2. Look for RECURRING patterns that appear ACROSS different sessions
3. Use search to find if similar issues occur in multiple conversations
4. Only report issues with evidence from 2+ different sessions
5. Be highly selective - most issues should NOT be reported

Focus on: patterns that REPEAT across sessions, not one-time occurrences.

Start by listing the conversations, then look for cross-conversation patterns."""

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
