"""Weave integration for GoodNightApp dreaming observability.

Weave automatically traces all LLM calls (Anthropic, Bedrock) when initialized.
"""

import logging
import os

import weave

logger = logging.getLogger("good-night.observability.weave")

_initialized = False


def init_weave(project: str = "good-night-dreaming", api_key: str | None = None) -> bool:
    """Initialize Weave tracing. Auto-traces all LLM calls."""
    global _initialized

    if _initialized:
        return True

    try:
        if api_key:
            os.environ["WANDB_API_KEY"] = api_key

        if not os.environ.get("WANDB_API_KEY"):
            logger.warning("WANDB_API_KEY not set.")
            return False

        weave.init(project)
        _initialized = True
        logger.info(f"Weave initialized: {project}")
        return True

    except Exception as e:
        logger.warning(f"Failed to initialize Weave: {e}")
        return False


def is_initialized() -> bool:
    return _initialized
