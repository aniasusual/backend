"""
Lowkey Context Management Package.

Exports:
- ContextConfig
- TokenEstimator
- ContextSquasher
- ContextCompactor
- ContextManager
- Recency Anchors
"""

from context.config import (
    ContextConfig,
    ALERT_EVICTION_MARKER,
    RECENCY_ANCHOR_DEFAULT,
    RECENCY_ANCHOR_CONFIRMATION,
    RECENCY_ANCHOR_ERROR,
    RECENCY_ANCHOR_CONVERSATIONAL,
    RECENCY_ANCHOR_FIRST_MESSAGE,
)
from context.estimator import TokenEstimator
from context.squasher import ContextSquasher
from context.compactor import ContextCompactor
from context.static_layer import StaticLayerManager
from context.manager import ContextManager

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


