from abc import ABC
from pathlib import Path
from typing import Optional, Any, Callable


class BaseSubagent(ABC):
    """
    Abstract base class for all specialized domain subagents.
    Provides standard sandbox context and execution interface.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = "qwen2.5-coder:7b",
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Callable[[dict], None]] = None,
        **kwargs,
    ):
        self.sandbox_path = Path(sandbox_path).resolve() if sandbox_path else None
        self.model_name = model_name
        self.tool_registry = tool_registry
        self.event_callback = event_callback

