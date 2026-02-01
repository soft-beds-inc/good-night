"""Observability module for GoodNightApp.

- init_weave(): Initialize Weave to auto-trace all LLM calls
- run_resolution_evaluation(): Run LLM judges on resolutions (traced by Weave)
"""

from .judges import run_resolution_evaluation
from .weave_integration import init_weave, is_initialized

__all__ = [
    "init_weave",
    "is_initialized",
    "run_resolution_evaluation",
]
