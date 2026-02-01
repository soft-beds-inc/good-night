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


ANALYSIS_BASE_PROMPT = """You are analyzing AI assistant conversations to find issues and patterns.

You have tools to explore conversations - use them to navigate and search efficiently.
Report each issue you find using the report_issue tool.

Your task:
1. Start by listing conversations to see what's available
2. Explore messages systematically, looking for patterns
3. Use search to find specific issues (errors, frustration signals, repeated requests)
4. Report issues you find with evidence (session_id, message_index, quotes)
5. Be thorough but efficient - use search to find relevant sections

Issue types to look for:
- repeated_request: User asks for the same thing multiple times
- frustration_signal: User shows frustration or dissatisfaction
- style_mismatch: AI response style doesn't match user expectations
- capability_gap: AI couldn't do something the user expected
- knowledge_gap: AI lacked knowledge the user expected
- other: Any other significant issue

When reporting issues:
- Include specific evidence with session_id and message_index
- Quote relevant text to support your findings
- Suggest potential resolutions when possible
- Prioritize by severity (critical > high > medium > low)

Be concise but thorough. Don't miss patterns that span multiple conversations.
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

        return f"""Analyze {len(conversations)} conversations for issues.

Conversation Summary:
- Total conversations: {len(conversations)}
- Total messages: {total_messages}
- Human messages: {human_messages}

Your task:
1. List conversations to see what's available
2. Explore messages, looking for patterns (use search and pagination)
3. Report issues you find using the report_issue tool
4. Be thorough but efficient - use search to find relevant sections

Focus on: repeated requests, user frustration, style mismatches, capability gaps.

Start by listing the conversations, then systematically analyze them."""

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
