"""Provider factory for creating agent providers."""

from typing import Any

from ..config import Config, load_config
from .anthropic_provider import AnthropicProvider
from .base import AgentProvider
from .bedrock_provider import BedrockProvider


class ProviderFactory:
    """Factory for creating agent providers based on configuration."""

    _providers: dict[str, type[AgentProvider]] = {
        "anthropic": AnthropicProvider,
        "bedrock": BedrockProvider,
    }

    @classmethod
    def create(
        cls,
        provider_name: str | None = None,
        config: Config | None = None,
        **kwargs: Any,
    ) -> AgentProvider:
        """
        Create an agent provider.

        Args:
            provider_name: Name of the provider (anthropic, bedrock)
            config: Optional config object. If not provided, loads from default location.
            **kwargs: Additional arguments passed to the provider constructor

        Returns:
            AgentProvider instance
        """
        if config is None:
            config = load_config()

        if provider_name is None:
            provider_name = config.provider.default

        if provider_name not in cls._providers:
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available: {list(cls._providers.keys())}"
            )

        provider_class = cls._providers[provider_name]

        # Build provider-specific kwargs
        if provider_name == "anthropic":
            if "model" not in kwargs:
                kwargs["model"] = config.provider.anthropic.model
        elif provider_name == "bedrock":
            if "region" not in kwargs:
                kwargs["region"] = config.provider.bedrock.region
            if "model" not in kwargs:
                kwargs["model"] = config.provider.bedrock.model

        return provider_class(**kwargs)

    @classmethod
    def register(cls, name: str, provider_class: type[AgentProvider]) -> None:
        """Register a new provider type."""
        cls._providers[name] = provider_class

    @classmethod
    def available_providers(cls) -> list[str]:
        """Return list of available provider names."""
        return list(cls._providers.keys())
