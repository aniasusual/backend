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
)

__all__ = [
    "ContextConfig",
    "ALERT_EVICTION_MARKER",
    "TokenEstimator",
    "ContextSquasher",
    "ContextCompactor",
    "StaticLayerManager",
    "ContextManager",
]

