"""Base class for agent providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .types import AgentConfig, AgentResponse, Message


class AgentProvider(ABC):
    """Abstract base class for AI agent providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this provider."""
        ...

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming responses."""
        ...

    @property
    @abstractmethod
    def supports_tools(self) -> bool:
        """Whether this provider supports tool use."""
        ...

    @abstractmethod
    async def query(
        self,
        messages: list[Message],
        config: AgentConfig,
        stream: bool = False,
    ) -> AgentResponse | AsyncIterator[Message]:
        """
        Send a query to the provider.

        Args:
            messages: List of messages in the conversation
            config: Agent configuration
            stream: Whether to stream the response

        Returns:
            AgentResponse if not streaming, AsyncIterator[Message] if streaming
        """
        ...

    @abstractmethod
    async def run_agent(
        self,
        initial_message: str,
        config: AgentConfig,
    ) -> AgentResponse:
        """
        Run an agent with the given configuration.

        This method handles the full agent loop including tool calls.

        Args:
            initial_message: The initial user message
            config: Agent configuration including tools

        Returns:
            AgentResponse with all messages and total usage
        """
        ...


class BaseAgent:
    """Base class for agents created by providers."""

    def __init__(self, provider: AgentProvider, config: AgentConfig):
        self.provider = provider
        self.config = config
        self.messages: list[Message] = []

    async def send(self, message: str) -> AgentResponse:
        """Send a message to the agent and get a response."""
        return await self.provider.run_agent(message, self.config)
