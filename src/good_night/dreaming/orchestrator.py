"""Main dreaming workflow orchestrator."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from ..config import Config, load_config
from ..connectors.factory import ConnectorFactory
from ..observability import init_weave
from ..providers.bedrock_provider import AWSAuthenticationError
from ..providers.factory import ProviderFactory
from ..storage.state import StateManager
from .events import AgentEvent, AgentEventStream
from .step1_analysis import AnalysisStep
from .step2_comparison import ComparisonStep
from .step3_resolution import ResolutionStep

logger = logging.getLogger("good-night.orchestrator")


@dataclass
class DreamingStatistics:
    """Statistics for a dreaming cycle with cost calculation."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str = ""

    # Pricing per 1M tokens (USD) - Claude Sonnet 4
    # https://www.anthropic.com/pricing
    PRICING = {
        "claude-sonnet-4-20250514": {
            "input": 3.00,
            "output": 15.00,
            "cache_write": 3.75,  # 1.25x input
            "cache_read": 0.30,   # 0.1x input
        },
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {  # Bedrock
            "input": 3.00,
            "output": 15.00,
            "cache_write": 3.75,
            "cache_read": 0.30,
        },
        "default": {
            "input": 3.00,
            "output": 15.00,
            "cache_write": 3.75,
            "cache_read": 0.30,
        },
    }

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def get_cost_usd(self) -> float:
        """Calculate total cost in USD."""
        pricing = self.PRICING.get(self.model, self.PRICING["default"])

        # Non-cached input = total input - cache_read
        non_cached_input = max(0, self.input_tokens - self.cache_read_tokens)

        cost = (
            (non_cached_input / 1_000_000) * pricing["input"]
            + (self.output_tokens / 1_000_000) * pricing["output"]
            + (self.cache_write_tokens / 1_000_000) * pricing["cache_write"]
            + (self.cache_read_tokens / 1_000_000) * pricing["cache_read"]
        )
        return cost

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.get_cost_usd(), 4),
            "model": self.model,
        }


@dataclass
class DreamingResult:
    """Result of a dreaming cycle."""

    success: bool = True
    error: str | None = None
    no_new_conversations: bool = False  # True when there were no new conversations to analyze
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversations_analyzed: int = 0
    issues_found: int = 0
    resolutions_generated: int = 0
    duration_seconds: float = 0.0
    resolution_files: list[Path] = field(default_factory=list)
    statistics: DreamingStatistics = field(default_factory=DreamingStatistics)


class DreamingOrchestrator:
    """Orchestrates the 3-step dreaming workflow."""

    def __init__(
        self,
        runtime_dir: Path | None = None,
        config: Config | None = None,
        dry_run: bool = False,
        event_stream: AgentEventStream | None = None,
    ):
        if runtime_dir is None:
            runtime_dir = Path.home() / ".good-night"

        self.runtime_dir = runtime_dir
        self.config = config or load_config(runtime_dir)
        self.dry_run = dry_run
        self.event_stream = event_stream or AgentEventStream()

        self.state_manager = StateManager(runtime_dir)
        self._connector_filter: list[str] | None = None
        self._prompt_filter: list[str] | None = None
        self._event_callback: Callable[[AgentEvent], None] | None = None
        self._conversation_limit: int | None = None  # Override for testing

    def set_connector_filter(self, connectors: list[str]) -> None:
        """Set filter for which connectors to process."""
        self._connector_filter = connectors

    def set_prompt_filter(self, prompts: list[str]) -> None:
        """Set filter for which prompts to run."""
        self._prompt_filter = prompts

    def set_conversation_limit(self, limit: int) -> None:
        """Set limit for number of conversations (for testing)."""
        self._conversation_limit = limit

    def set_event_callback(self, callback: Callable[[AgentEvent], None]) -> None:
        """Set callback for event notifications."""
        self._event_callback = callback
        self.event_stream.subscribe(callback)

    def get_event_stream(self) -> AgentEventStream:
        """Get the event stream for this orchestrator."""
        return self.event_stream

    async def run(self) -> DreamingResult:
        """
        Run the full dreaming cycle.

        Returns:
            DreamingResult with cycle statistics
        """
        start_time = datetime.now()
        run_id = str(uuid.uuid4())
        result = DreamingResult(run_id=run_id)

        # Initialize Weave tracing (auto-traces LLM calls)
        # Uses WANDB_API_KEY from environment
        init_weave()

        # Start event stream
        self.event_stream.start(run_id)

        try:
            logger.info(f"Starting dreaming cycle {run_id}")

            # Emit cycle start event
            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id="orchestrator",
                agent_type="orchestrator",
                event_type="thinking",
                summary=f"Starting dreaming cycle {run_id[:8]}",
            ))

            # Initialize provider
            provider = ProviderFactory.create(config=self.config)

            # Get connectors
            connector_ids = self._connector_filter or self.config.enabled.connectors
            connectors = ConnectorFactory.create_all(self.runtime_dir, connector_ids)

            if not connectors:
                logger.warning("No connectors available")
                result.error = "No connectors available"
                return result

            # Process each connector
            total_issues = 0
            total_resolutions = 0
            total_conversations = 0

            # Token tracking
            stats = DreamingStatistics(model=self.config.provider.bedrock.model if self.config.provider.default == "bedrock" else self.config.provider.anthropic.model)

            for connector in connectors:
                logger.info(f"Processing connector: {connector.connector_id}")

                self.event_stream.emit(AgentEvent(
                    timestamp=datetime.now(),
                    agent_id="orchestrator",
                    agent_type="orchestrator",
                    event_type="thinking",
                    summary=f"Processing connector: {connector.connector_id}",
                ))

                # Step 0: Extract conversations
                conversations = await self._extract_conversations(connector)
                total_conversations += len(conversations)

                if not conversations:
                    logger.info(f"No new conversations for {connector.connector_id}")
                    continue

                # Step 1: Analysis
                analysis_step = AnalysisStep(
                    self.runtime_dir,
                    self.config,
                    provider,
                    event_stream=self.event_stream,
                )
                report = await analysis_step.analyze(
                    connector, conversations, self._prompt_filter
                )
                total_issues += len(report.issues)

                # Track step1 tokens
                stats.input_tokens += report.token_usage.input_tokens
                stats.output_tokens += report.token_usage.output_tokens
                stats.cache_read_tokens += report.token_usage.cache_read_tokens
                stats.cache_write_tokens += report.token_usage.cache_write_tokens

                if not report.issues:
                    logger.info(f"No issues found for {connector.connector_id}")
                    continue

                # Step 2: Historical comparison
                comparison_step = ComparisonStep(
                    self.runtime_dir,
                    self.config,
                    provider=provider,
                    event_stream=self.event_stream,
                )
                enriched_report = await comparison_step.compare(report)

                # Track step2 tokens (enriched report accumulates step1 + step2, so subtract step1)
                stats.input_tokens += enriched_report.token_usage.input_tokens - report.token_usage.input_tokens
                stats.output_tokens += enriched_report.token_usage.output_tokens - report.token_usage.output_tokens
                stats.cache_read_tokens += enriched_report.token_usage.cache_read_tokens - report.token_usage.cache_read_tokens
                stats.cache_write_tokens += enriched_report.token_usage.cache_write_tokens - report.token_usage.cache_write_tokens

                logger.info(
                    f"Issues: {len(enriched_report.new_issues)} new, "
                    f"{len(enriched_report.recurring_issues)} recurring, "
                    f"{len(enriched_report.resolved_issues)} resolved"
                )

                # Step 3: Resolution generation
                resolution_step = ResolutionStep(
                    self.runtime_dir,
                    self.config,
                    provider,
                    event_stream=self.event_stream,
                )
                resolution, resolution_file = await resolution_step.generate(
                    enriched_report, run_id, dry_run=self.dry_run
                )

                if resolution:
                    action_count = sum(
                        len(cr.actions) for cr in resolution.resolutions
                    )
                    total_resolutions += action_count
                    if resolution_file:
                        result.resolution_files.append(resolution_file)

                    # Track step3 tokens from resolution metadata
                    if "token_usage" in resolution.metadata:
                        s3 = resolution.metadata["token_usage"]
                        stats.input_tokens += s3.get("input_tokens", 0)
                        stats.output_tokens += s3.get("output_tokens", 0)
                        stats.cache_read_tokens += s3.get("cache_read_tokens", 0)
                        stats.cache_write_tokens += s3.get("cache_write_tokens", 0)

                # Update connector state (even if no issues found, we still processed the conversations)
                if conversations and not self.dry_run:
                    # Normalize timestamps to avoid comparing naive and aware datetimes
                    def normalize_ts(ts: datetime | None) -> datetime | None:
                        if ts is None:
                            return None
                        # Make all timestamps timezone-aware (UTC)
                        if ts.tzinfo is None:
                            from datetime import timezone
                            return ts.replace(tzinfo=timezone.utc)
                        return ts

                    timestamps = [
                        normalize_ts(c.ended_at) or normalize_ts(c.started_at)
                        for c in conversations
                    ]
                    # Filter out None values
                    valid_timestamps = [ts for ts in timestamps if ts is not None]
                    latest_ts = max(valid_timestamps) if valid_timestamps else None
                    self.state_manager.update_connector_state(
                        connector.connector_id,
                        last_processed=latest_ts,
                        conversations_processed=len(conversations),
                    )

            # Check if no new conversations were found
            if total_conversations == 0:
                result.no_new_conversations = True
                result.duration_seconds = (datetime.now() - start_time).total_seconds()

                self.event_stream.emit(AgentEvent(
                    timestamp=datetime.now(),
                    agent_id="orchestrator",
                    agent_type="orchestrator",
                    event_type="complete",
                    summary="No new conversations to analyze",
                ))

                logger.info("No new conversations to analyze")
                return result

            # Update dreaming state
            if not self.dry_run:
                self.state_manager.update_dreaming_state(
                    run_id=run_id,
                    issues_found=total_issues,
                    resolutions_generated=total_resolutions,
                )

            # Build result
            result.conversations_analyzed = total_conversations
            result.issues_found = total_issues
            result.resolutions_generated = total_resolutions
            result.duration_seconds = (datetime.now() - start_time).total_seconds()

            # Add token statistics
            result.statistics = stats

            # Emit completion event
            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id="orchestrator",
                agent_type="orchestrator",
                event_type="complete",
                summary=f"Cycle complete: {total_issues} issues, {total_resolutions} resolutions",
                details={
                    "conversations": total_conversations,
                    "issues": total_issues,
                    "resolutions": total_resolutions,
                    "duration_seconds": result.duration_seconds,
                    "statistics": result.statistics.to_dict(),
                },
            ))

            logger.info(
                f"Dreaming cycle completed: {total_conversations} conversations, "
                f"{total_issues} issues, {total_resolutions} resolutions"
            )

        except AWSAuthenticationError as e:
            # Handle AWS auth errors with helpful message
            error_msg = str(e)
            if e.hint:
                error_msg = f"{e}: {e.hint}"
            logger.error(f"AWS authentication failed: {error_msg}")
            result.success = False
            result.error = error_msg

            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id="orchestrator",
                agent_type="orchestrator",
                event_type="error",
                summary=error_msg,
            ))

        except Exception as e:
            logger.exception(f"Dreaming cycle failed: {e}")
            result.success = False
            result.error = str(e)

            self.event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id="orchestrator",
                agent_type="orchestrator",
                event_type="error",
                summary=f"Cycle failed: {str(e)[:80]}",
            ))

        finally:
            # Stop event stream
            self.event_stream.stop()

        return result

    async def _extract_conversations(self, connector) -> list:
        """Extract conversations from a connector.

        Logic:
        - If --limit is set: use that limit (for testing)
        - If first run (no last_processed): look back initial_lookback_days
        - Otherwise: get all conversations since last_processed (no limit)
        """
        state = self.state_manager.get_connector_state(connector.connector_id)

        # Override mode: use explicit limit (for testing)
        if self._conversation_limit is not None:
            batch = await connector.extract_conversations(
                since=state.last_processed,
                limit=self._conversation_limit,
            )
            return batch.conversations

        # First run: no last_processed, use initial_lookback_days
        if state.last_processed is None:
            lookback_days = self.config.dreaming.initial_lookback_days
            since = datetime.now() - timedelta(days=lookback_days)
            logger.info(f"First run for {connector.connector_id}, looking back {lookback_days} days")
        else:
            # Subsequent runs: get all since last processed
            since = state.last_processed
            logger.info(f"Resuming from {since.isoformat()} for {connector.connector_id}")

        # No limit - get all conversations since the cutoff
        batch = await connector.extract_conversations(since=since, limit=None)
        return batch.conversations
