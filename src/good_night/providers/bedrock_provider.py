"""AWS Bedrock provider implementation."""

import json
import os
from typing import Any, AsyncIterator

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


class AWSAuthenticationError(Exception):
    """Raised when AWS authentication fails."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


class BedrockProvider(AgentProvider):
    """Provider implementation using AWS Bedrock."""

    def __init__(
        self,
        region: str = "us-east-1",
        model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    ):
        self.region = region
        self.model = model
        self._client = None

    @property
    def client(self) -> Any:
        """Lazy-load boto3 client."""
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "boto3 is required for Bedrock provider. "
                    "Install with: pip install boto3"
                )

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
            )
        return self._client

    @property
    def provider_name(self) -> str:
        return "bedrock"

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supports_tools(self) -> bool:
        return True

    def _convert_messages_to_bedrock(
        self, messages: list[Message]
    ) -> list[dict[str, Any]]:
        """Convert internal messages to Bedrock/Anthropic format."""
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

    def _convert_tools_to_bedrock(self, config: AgentConfig) -> list[dict[str, Any]]:
        """Convert tool definitions to Bedrock format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in config.tools
        ]

    def _parse_bedrock_response(
        self, response_body: dict[str, Any]
    ) -> tuple[Message, TokenUsage]:
        """Parse Bedrock response into internal format."""
        content_text = ""
        tool_calls: list[ToolCall] = []

        for block in response_body.get("content", []):
            if block.get("type") == "text":
                content_text = block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    input=block.get("input", {}),
                ))

        message = Message(
            role=MessageRole.ASSISTANT,
            content=content_text if content_text else None,
            tool_calls=tool_calls if tool_calls else None,
        )

        usage_data = response_body.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
        )

        return message, usage

    async def query(
        self,
        messages: list[Message],
        config: AgentConfig,
        stream: bool = False,
    ) -> AgentResponse | AsyncIterator[Message]:
        """Send a query to Bedrock."""
        bedrock_messages = self._convert_messages_to_bedrock(messages)
        tools = self._convert_tools_to_bedrock(config) if config.tools else None

        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": config.max_tokens,
            "messages": bedrock_messages,
        }

        if config.system_prompt:
            body["system"] = config.system_prompt

        if tools:
            body["tools"] = tools

        if config.temperature:
            body["temperature"] = config.temperature

        # Bedrock uses synchronous API, run in executor
        import asyncio

        loop = asyncio.get_event_loop()

        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.client.invoke_model(
                    modelId=config.model or self.model,
                    body=json.dumps(body),
                ),
            )
        except Exception as e:
            # Handle AWS authentication errors with helpful messages
            error_str = str(e)
            if "Token has expired" in error_str or "TokenRetrievalError" in str(type(e)):
                raise AWSAuthenticationError(
                    "AWS SSO token has expired",
                    hint="Run 'aws sso login' to refresh your credentials",
                ) from e
            if "NoCredentialsError" in str(type(e)) or "Unable to locate credentials" in error_str:
                raise AWSAuthenticationError(
                    "AWS credentials not found",
                    hint="Configure AWS credentials with 'aws configure' or 'aws sso login'",
                ) from e
            if "ExpiredTokenException" in error_str:
                raise AWSAuthenticationError(
                    "AWS session token has expired",
                    hint="Run 'aws sso login' or refresh your session credentials",
                ) from e
            raise

        response_body = json.loads(response["body"].read())
        message, usage = self._parse_bedrock_response(response_body)

        return AgentResponse(
            messages=[message],
            usage=usage,
            stop_reason=response_body.get("stop_reason"),
        )

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
