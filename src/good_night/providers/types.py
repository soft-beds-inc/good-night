"""Unified types for provider abstraction."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine


class MessageRole(str, Enum):
    """Role of a message in a conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@dataclass
class ToolCall:
    """A tool call made by the assistant."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    """Result of a tool call."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """Unified message format across providers."""

    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_result: ToolResult | None = None
    timestamp: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        result: dict[str, Any] = {"role": self.role.value}

        if self.content is not None:
            result["content"] = self.content

        if self.tool_calls:
            result["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "input": tc.input} for tc in self.tool_calls
            ]

        if self.tool_result:
            result["tool_result"] = {
                "tool_call_id": self.tool_result.tool_call_id,
                "content": self.tool_result.content,
                "is_error": self.tool_result.is_error,
            }

        if self.timestamp:
            result["timestamp"] = self.timestamp.isoformat()

        return result


@dataclass
class TokenUsage:
    """Token usage tracking."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary for serialization."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


@dataclass
class ToolDefinition:
    """Definition of a tool that can be used by an agent."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Coroutine[Any, Any, str]] | None = None


@dataclass
class AgentConfig:
    """Configuration for an agent."""

    model: str | None = None  # None = use provider default
    system_prompt: str = ""
    tools: list[ToolDefinition] = field(default_factory=list)
    max_turns: int = 10
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class AgentResponse:
    """Response from an agent query."""

    messages: list[Message]
    usage: TokenUsage
    stop_reason: str | None = None
