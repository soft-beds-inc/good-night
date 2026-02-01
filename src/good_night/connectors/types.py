"""Types for source connectors."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    """Role of a message in a conversation."""

    HUMAN = "human"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"


@dataclass
class ConversationMessage:
    """A single message in a conversation."""

    role: MessageRole
    content: str
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # For tool messages
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result: dict[str, Any] = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.timestamp:
            result["timestamp"] = self.timestamp.isoformat()
        if self.metadata:
            result["metadata"] = self.metadata
        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.tool_input:
            result["tool_input"] = self.tool_input
        if self.tool_result:
            result["tool_result"] = self.tool_result
        return result


@dataclass
class Conversation:
    """A complete conversation session."""

    session_id: str
    messages: list[ConversationMessage]
    started_at: datetime
    ended_at: datetime | None = None
    source_type: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        """Get conversation duration in seconds."""
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()

    @property
    def message_count(self) -> int:
        """Get total number of messages."""
        return len(self.messages)

    @property
    def human_messages(self) -> list[ConversationMessage]:
        """Get only human messages."""
        return [m for m in self.messages if m.role == MessageRole.HUMAN]

    @property
    def assistant_messages(self) -> list[ConversationMessage]:
        """Get only assistant messages."""
        return [m for m in self.messages if m.role == MessageRole.ASSISTANT]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "messages": [m.to_dict() for m in self.messages],
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "source_type": self.source_type,
            "metadata": self.metadata,
        }


@dataclass
class ConversationBatch:
    """A batch of conversations from a connector."""

    conversations: list[Conversation]
    cursor: str | None = None
    has_more: bool = False

    @property
    def total_messages(self) -> int:
        """Get total messages across all conversations."""
        return sum(c.message_count for c in self.conversations)


@dataclass
class ConnectorSettings:
    """Settings parsed from a connector definition."""

    enabled: bool = True
    path: str = ""
    format: str = "jsonl"
    extra: dict[str, Any] = field(default_factory=dict)
