"""
Backward compatibility facade for Lowkey context management.

Re-exports core classes and functions from the modular `context` package.
"""
from context import (
    ContextConfig,
    ALERT_EVICTION_MARKER,
    TokenEstimator,
    ContextSquasher,
    ContextCompactor,
    StaticLayerManager,
    ContextManager,
    RECENCY_ANCHOR_DEFAULT,
    RECENCY_ANCHOR_CONFIRMATION,
    RECENCY_ANCHOR_ERROR,
    RECENCY_ANCHOR_CONVERSATIONAL,
    RECENCY_ANCHOR_FIRST_MESSAGE,
)

__all__ = [
    "ContextConfig",
    "ALERT_EVICTION_MARKER",
    "TokenEstimator",
    "ContextSquasher",
    "ContextCompactor",
    "StaticLayerManager",
    "ContextManager",
    "RECENCY_ANCHOR_DEFAULT",
    "RECENCY_ANCHOR_CONFIRMATION",
    "RECENCY_ANCHOR_ERROR",
    "RECENCY_ANCHOR_CONVERSATIONAL",
    "RECENCY_ANCHOR_FIRST_MESSAGE",
]

