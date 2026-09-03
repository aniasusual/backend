"""
Backward compatibility facade for Lowkey context management.

Re-exports core classes and functions from the modular `context` package.
"""

from context import (
    ContextConfig,
    TokenEstimator,
    ContextSquasher,
    ContextCompactor,
    ContextManager,
    RECENCY_ANCHOR_DEFAULT,
    RECENCY_ANCHOR_CONFIRMATION,
    RECENCY_ANCHOR_ERROR,
)

__all__ = [
    "ContextConfig",
    "TokenEstimator",
    "ContextSquasher",
    "ContextCompactor",
    "ContextManager",
    "RECENCY_ANCHOR_DEFAULT",
    "RECENCY_ANCHOR_CONFIRMATION",
    "RECENCY_ANCHOR_ERROR",
]
