"""Agent event streaming for observability."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass
class AgentEvent:
    """Event emitted by an agent during execution."""

    timestamp: datetime
    agent_id: str  # e.g., "step1-analysis", "step1-agent-2"
    agent_type: str  # "analysis", "comparison", "resolution"
    event_type: str  # "tool_call", "tool_result", "thinking", "complete", "error"
    tool_name: str | None = None  # For tool_call events
    summary: str = ""  # Truncated description (max 100 chars)
    details: dict[str, Any] | None = None  # Optional full details

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "event_type": self.event_type,
            "tool_name": self.tool_name,
            "summary": self.summary,
            "details": self.details,
        }


class AgentEventStream:
    """Manages agent event streaming."""

    def __init__(self, max_events: int = 1000):
        self._events: list[AgentEvent] = []
        self._max_events = max_events
        self._subscribers: list[Callable[[AgentEvent], None]] = []
        self._running = False
        self._run_id: str | None = None

    def start(self, run_id: str) -> None:
        """Start a new event stream session."""
        self._run_id = run_id
        self._running = True
        self._events.clear()

    def stop(self) -> None:
        """Stop the event stream session."""
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if stream is active."""
        return self._running

    @property
    def run_id(self) -> str | None:
        """Get current run ID."""
        return self._run_id

    def emit(self, event: AgentEvent) -> None:
        """Emit an event to all subscribers."""
        self._events.append(event)

        # Trim old events if exceeding max
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events :]

        # Notify all subscribers
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception:
                # Don't let subscriber errors break event emission
                pass

    def subscribe(self, callback: Callable[[AgentEvent], None]) -> None:
        """Subscribe to events."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[AgentEvent], None]) -> None:
        """Unsubscribe from events."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def get_recent(self, limit: int = 20) -> list[AgentEvent]:
        """Get recent events."""
        return self._events[-limit:]

    def get_all(self) -> list[AgentEvent]:
        """Get all events."""
        return list(self._events)

    def get_active_agents(self) -> dict[str, AgentEvent]:
        """Get last event for each active (non-complete) agent."""
        active: dict[str, AgentEvent] = {}
        completed: set[str] = set()

        for event in reversed(self._events):
            if event.event_type == "complete":
                completed.add(event.agent_id)
            elif event.agent_id not in active and event.agent_id not in completed:
                active[event.agent_id] = event

        return active

    def get_events_by_agent(self, agent_id: str) -> list[AgentEvent]:
        """Get all events for a specific agent."""
        return [e for e in self._events if e.agent_id == agent_id]


def create_event(
    agent_id: str,
    agent_type: str,
    event_type: str,
    tool_name: str | None = None,
    summary: str = "",
    details: dict[str, Any] | None = None,
) -> AgentEvent:
    """Helper to create an event with current timestamp."""
    return AgentEvent(
        timestamp=datetime.now(),
        agent_id=agent_id,
        agent_type=agent_type,
        event_type=event_type,
        tool_name=tool_name,
        summary=summary[:100] if summary else "",  # Truncate to 100 chars
        details=details,
    )
