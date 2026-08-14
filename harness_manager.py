import importlib
import inspect
from pathlib import Path
from typing import Dict, Type
from plugins.base import BaseHarness

class HarnessManager:
    def __init__(self, plugins_dir: str):
        self.plugins_dir = Path(plugins_dir)
        self.harnesses: Dict[str, Type[BaseHarness]] = {}
        self.load_plugins()

    def load_plugins(self):
        """Dynamically loads all harnesses from the plugins directory."""
        if not self.plugins_dir.exists():
            return
            
        for file in self.plugins_dir.glob("*.py"):
            if file.name == "__init__.py" or file.name == "base.py":
                continue
                
            module_name = f"plugins.{file.stem}"
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseHarness) and obj is not BaseHarness:
                        self.harnesses[obj.__name__] = obj
                        print(f"Loaded harness: {obj.__name__}")
            except Exception as e:
                print(f"Failed to load plugin {file.name}: {e}")

    def get_harness(self, name: str) -> BaseHarness:
        """Instantiates and returns the requested harness."""
        if name not in self.harnesses:
            raise ValueError(f"Harness {name} not found.")
        return self.harnesses[name]()
