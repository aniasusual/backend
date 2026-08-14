from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any

class BaseHarness(ABC):
    """
    Abstract Base Class for all Lowkey Harness Plugins.
    """
    
    @abstractmethod
    def process_prompt(self, user_prompt: str, context: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a user prompt and yield status/token updates.
        
        Args:
            user_prompt: The text input from the user.
            context: System context, including access to the ToolRegistry.
            
        Yields:
            Dict containing type (e.g. 'token', 'status', 'tool_call') and content.
        """
        pass
