"""Anthropic SDK provider implementation."""

import os
from typing import Any, AsyncIterator

import anthropic

from .base import AgentProvider
from .types import (
    AgentConfig,
    AgentResponse,
    Message,
    MessageRole,
    TokenUsage,
    ToolCall,
    ToolResult,
)


class AnthropicProvider(AgentProvider):
    """Provider implementation using the Anthropic SDK."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
        self.model = model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supports_tools(self) -> bool:
        return True

    def _convert_messages_to_anthropic(
        self, messages: list[Message]
    ) -> list[dict[str, Any]]:
        """Convert internal messages to Anthropic format."""
        result: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == MessageRole.USER:
                result.append({"role": "user", "content": msg.content or ""})

            elif msg.role == MessageRole.ASSISTANT:
                if msg.tool_calls:
                    content: list[dict[str, Any]] = []
                    if msg.content:
                        content.append({"type": "text", "text": msg.content})
                    for tc in msg.tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.input,
                        })
                    result.append({"role": "assistant", "content": content})
                else:
                    result.append({"role": "assistant", "content": msg.content or ""})

            elif msg.role == MessageRole.TOOL_RESULT and msg.tool_result:
                result.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_result.tool_call_id,
                        "content": msg.tool_result.content,
                        "is_error": msg.tool_result.is_error,
                    }],
                })

        return result

    def _convert_tools_to_anthropic(self, config: AgentConfig) -> list[dict[str, Any]]:
        """Convert tool definitions to Anthropic format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in config.tools
        ]

    def _parse_anthropic_response(
        self, response: anthropic.types.Message
    ) -> tuple[Message, TokenUsage]:
        """Parse Anthropic response into internal format."""
        content_text = ""
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content_text = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    input=block.input,  # type: ignore
                ))

        message = Message(
            role=MessageRole.ASSISTANT,
            content=content_text if content_text else None,
            tool_calls=tool_calls if tool_calls else None,
        )

        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        )

        return message, usage

    async def query(
        self,
        messages: list[Message],
        config: AgentConfig,
        stream: bool = False,
    ) -> AgentResponse | AsyncIterator[Message]:
        """Send a query to Anthropic."""
        anthropic_messages = self._convert_messages_to_anthropic(messages)
        tools = self._convert_tools_to_anthropic(config) if config.tools else None

        kwargs: dict[str, Any] = {
            "model": config.model or self.model,
            "max_tokens": config.max_tokens,
            "messages": anthropic_messages,
        }

        if config.system_prompt:
            # Enable prompt caching for system prompt
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": config.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        if tools:
            kwargs["tools"] = tools

        if config.temperature:
            kwargs["temperature"] = config.temperature

        if stream:
            return self._stream_response(kwargs)

        response = await self.client.messages.create(**kwargs)
        message, usage = self._parse_anthropic_response(response)

        return AgentResponse(
            messages=[message],
            usage=usage,
            stop_reason=response.stop_reason,
        )

    async def _stream_response(self, kwargs: dict[str, Any]) -> AsyncIterator[Message]:
        """Stream response from Anthropic."""
        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield Message(role=MessageRole.ASSISTANT, content=text)

    async def run_agent(
        self,
        initial_message: str,
        config: AgentConfig,
    ) -> AgentResponse:
        """Run an agent loop with tool handling."""
        messages: list[Message] = [
            Message(role=MessageRole.USER, content=initial_message)
        ]
        total_usage = TokenUsage()
        all_messages: list[Message] = list(messages)

        for _ in range(config.max_turns):
            response = await self.query(messages, config, stream=False)
            assert isinstance(response, AgentResponse)

            total_usage = total_usage + response.usage
            assistant_message = response.messages[0]
            all_messages.append(assistant_message)
            messages.append(assistant_message)

            # Check if we should stop
            if response.stop_reason == "end_turn" or not assistant_message.tool_calls:
                return AgentResponse(
                    messages=all_messages,
                    usage=total_usage,
                    stop_reason=response.stop_reason,
                )

            # Handle tool calls
            for tool_call in assistant_message.tool_calls:
                tool_result = await self._execute_tool(tool_call, config)
                tool_result_message = Message(
                    role=MessageRole.TOOL_RESULT,
                    tool_result=tool_result,
                )
                all_messages.append(tool_result_message)
                messages.append(tool_result_message)

        return AgentResponse(
            messages=all_messages,
            usage=total_usage,
            stop_reason="max_turns",
        )

    async def _execute_tool(
        self, tool_call: ToolCall, config: AgentConfig
    ) -> ToolResult:
        """Execute a tool call."""
        for tool in config.tools:
            if tool.name == tool_call.name and tool.handler:
                try:
                    result = await tool.handler(**tool_call.input)
                    return ToolResult(
                        tool_call_id=tool_call.id,
                        content=result,
                        is_error=False,
                    )
                except Exception as e:
                    return ToolResult(
                        tool_call_id=tool_call.id,
                        content=str(e),
                        is_error=True,
                    )

        return ToolResult(
            tool_call_id=tool_call.id,
            content=f"Unknown tool: {tool_call.name}",
            is_error=True,
        )
