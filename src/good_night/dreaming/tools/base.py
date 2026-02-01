"""Base utilities for tool creation."""

from datetime import datetime
from typing import Any, Callable, Coroutine

from ...providers.types import ToolDefinition
from ..events import AgentEvent, AgentEventStream


class ToolBuilder:
    """Builder for creating tool definitions with common patterns."""

    @staticmethod
    def create(
        name: str,
        description: str,
        handler: Callable[..., Coroutine[Any, Any, str]],
        properties: dict[str, Any] | None = None,
        required: list[str] | None = None,
    ) -> ToolDefinition:
        """
        Create a tool definition.

        Args:
            name: Tool name
            description: Tool description
            handler: Async handler function
            properties: JSON schema properties
            required: List of required property names

        Returns:
            ToolDefinition
        """
        input_schema: dict[str, Any] = {
            "type": "object",
            "properties": properties or {},
        }
        if required:
            input_schema["required"] = required

        return ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )


def wrap_tool_with_events(
    tool: ToolDefinition,
    agent_id: str,
    agent_type: str,
    event_stream: AgentEventStream,
) -> ToolDefinition:
    """
    Wrap a tool handler to emit events on calls and results.

    Args:
        tool: Original tool definition
        agent_id: ID of the agent using this tool
        agent_type: Type of agent (analysis, comparison, resolution)
        event_stream: Event stream to emit to

    Returns:
        New ToolDefinition with wrapped handler
    """
    original_handler = tool.handler
    if original_handler is None:
        return tool

    async def wrapped_handler(**kwargs: Any) -> str:
        # Emit tool_call event
        args_summary = _summarize_args(kwargs)
        event_stream.emit(AgentEvent(
            timestamp=datetime.now(),
            agent_id=agent_id,
            agent_type=agent_type,
            event_type="tool_call",
            tool_name=tool.name,
            summary=f"{tool.name}({args_summary})"[:100],
            details={"args": kwargs},
        ))

        try:
            result = await original_handler(**kwargs)

            # Emit tool_result event with meaningful summary
            result_summary = _extract_result_summary(tool.name, result)
            event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id=agent_id,
                agent_type=agent_type,
                event_type="tool_result",
                tool_name=tool.name,
                summary=result_summary[:100],
                details={"result_length": len(result)},
            ))

            return result

        except Exception as e:
            # Emit error event
            event_stream.emit(AgentEvent(
                timestamp=datetime.now(),
                agent_id=agent_id,
                agent_type=agent_type,
                event_type="error",
                tool_name=tool.name,
                summary=f"{tool.name} error: {str(e)}"[:100],
                details={"error": str(e)},
            ))
            raise

    return ToolDefinition(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        handler=wrapped_handler,
    )


def _extract_result_summary(tool_name: str, result: str) -> str:
    """Extract a meaningful summary from a tool result."""
    import json as json_module

    try:
        data = json_module.loads(result)
    except (json_module.JSONDecodeError, TypeError):
        # Not JSON, return truncated string
        return f"{tool_name}: {result[:60]}..." if len(result) > 60 else f"{tool_name}: {result}"

    # Extract meaningful info based on common patterns
    if "error" in data:
        return f"{tool_name}: ERROR - {data['error'][:60]}"

    if "success" in data:
        msg = data.get("message", "")
        if msg:
            return f"{tool_name}: {msg[:70]}"
        return f"{tool_name}: success={data['success']}"

    if "total" in data:
        total = data["total"]
        if "conversations" in data:
            return f"{tool_name}: {total} conversations"
        if "issues" in data:
            return f"{tool_name}: {total} issues"
        if "results" in data:
            count = len(data["results"])
            return f"{tool_name}: {count} results (of {total})"
        if "resolutions" in data:
            return f"{tool_name}: {total} resolutions"
        if "pending_actions" in data:
            return f"{tool_name}: {total} pending actions"
        return f"{tool_name}: total={total}"

    if "messages" in data:
        count = len(data.get("messages", []))
        has_more = data.get("has_more", False)
        return f"{tool_name}: {count} messages" + (" (more available)" if has_more else "")

    if "recommendation" in data:
        return f"{tool_name}: {data['recommendation'][:70]}"

    if "issue_id" in data:
        return f"{tool_name}: issue {data['issue_id'][:8]}"

    if "action_id" in data:
        return f"{tool_name}: action {data['action_id']}"

    # Fallback: list top-level keys
    keys = list(data.keys())[:3]
    return f"{tool_name}: {{{', '.join(keys)}...}}"


def _summarize_args(kwargs: dict[str, Any], max_len: int = 60) -> str:
    """Create a short summary of arguments."""
    if not kwargs:
        return ""

    parts = []
    total_len = 0

    for key, value in kwargs.items():
        if isinstance(value, str):
            val_str = f'"{value[:20]}..."' if len(value) > 20 else f'"{value}"'
        elif isinstance(value, (list, dict)):
            val_str = f"<{type(value).__name__}>"
        else:
            val_str = str(value)

        part = f"{key}={val_str}"
        if total_len + len(part) > max_len:
            parts.append("...")
            break
        parts.append(part)
        total_len += len(part) + 2

    return ", ".join(parts)
