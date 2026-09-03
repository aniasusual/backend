import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    import yaml
except ImportError:
    yaml = None


AGENTS_CONFIG_DIR = Path(__file__).parent / "agents"


ALL_STANDARD_TOOLS: List[str] = [
    "read_file",
    "view_bulk",
    "glob_files",
    "grep_search",
    "write_file",
    "write_files",
    "edit_file",
    "insert_text",
    "list_directory",
    "lint_javascript",
    "get_assets",
    "ask_human",
    "finish",
    "execute_command",
    "run_background_command",
    "stop_background_command",
]

ALL_SUBAGENTS: List[str] = [
    "invoke_design_agent",
    "invoke_troubleshoot_agent",
    "invoke_vision_agent",
    "test_ui",
]


@dataclass
class AgentProfile:
    """
    Structured runtime profile governing model-specific tool whitelists,
    subagent activations, token budgeting, and reasoning flags.
    """
    id: str
    name: str
    tier: int
    context_window: int = 32000
    max_iterations: int = 30
    prompt_id: str = "master_agent"
    is_reasoning_model: bool = False
    strip_think_tags: bool = False
    text_fallback_parser: bool = True
    whitelisted_tools: List[str] = field(default_factory=lambda: list(ALL_STANDARD_TOOLS))
    enabled_subagents: List[str] = field(default_factory=lambda: list(ALL_SUBAGENTS))
    target_models: List[str] = field(default_factory=list)

    @property
    def all_callable_tools(self) -> List[str]:
        """Returns the full list of tool identifiers callable by this model."""
        combined = list(self.whitelisted_tools)
        for sa in self.enabled_subagents:
            if sa not in combined:
                combined.append(sa)
            short_name = sa.replace("invoke_", "")
            if short_name not in combined:
                combined.append(short_name)
        return combined


class AgentLoader:
    """
    Dynamically loads and resolves model-specific agent profiles from YAML definitions.
    Inspired by Emergent's Cortex agent spec loader.
    """

    _cache: Dict[str, AgentProfile] = {}
    _model_to_profile_id: Dict[str, str] = {}

    @classmethod
    def load_all_profiles(cls, config_dir: Optional[Path] = None) -> Dict[str, AgentProfile]:
        """Loads all agent YAML specs from the config directory."""
        target_dir = config_dir or AGENTS_CONFIG_DIR
        profiles = {}

        if not target_dir.exists():
            return profiles

        for yaml_file in target_dir.glob("*.yaml"):
            try:
                profile = cls._parse_yaml_file(yaml_file)
                if profile:
                    profiles[profile.id] = profile
                    for model_name in profile.target_models:
                        cls._model_to_profile_id[model_name.lower()] = profile.id
            except Exception as e:
                print(f"[AgentLoader] Error loading {yaml_file.name}: {e}")

        cls._cache = profiles
        return profiles

    @classmethod
    def get_profile_for_model(cls, model_name: str) -> AgentProfile:
        """
        Resolves a model name (e.g. 'qwen2.5-coder:7b', 'deepseek-r1:8b', 'qwen2.5-coder:32b')
        to its tailored AgentProfile.
        """
        if not cls._cache:
            cls.load_all_profiles()

        clean_name = (model_name or "").lower().strip()

        # 1. Exact match in target_models
        if clean_name in cls._model_to_profile_id:
            profile_id = cls._model_to_profile_id[clean_name]
            if profile_id in cls._cache:
                return cls._cache[profile_id]

        # 2. Pattern Matching Heuristics
        # Reasoning models (R1)
        if "r1" in clean_name or "reasoner" in clean_name or "deepseek-r1" in clean_name:
            return cls._cache.get("deepseek_r1_reasoning", cls._fallback_profile())

        # Cloud Frontier Models (claude, gpt, opus, sonnet, gemini)
        if any(s in clean_name for s in ["claude", "gpt", "opus", "sonnet", "gemini"]):
            return cls._cache.get("cloud_frontier", cls._cache.get("qwen2.5_coder_14b_32b", cls._fallback_profile()))

        # Codestral Models
        if "codestral" in clean_name:
            return cls._cache.get("codestral_22b", cls._cache.get("qwen2.5_coder_14b_32b", cls._fallback_profile()))

        # Workstation & Intermediate Models (14b, 15b, 16b, 13b, 32b, 34b, 35b, 70b)
        if any(s in clean_name for s in ["14b", "15b", "16b", "13b", "32b", "34b", "35b", "70b"]):
            return cls._cache.get("qwen2.5_coder_14b_32b", cls._fallback_profile())

        # Ultra-Lightweight Models (1.5b, 3b, tiny)
        if any(s in clean_name for s in ["1.5b", "3b", "tiny"]):
            return cls._cache.get("qwen2.5_coder_1.5b_3b", cls._cache.get("qwen2.5_coder_7b", cls._fallback_profile()))

        # Default: Standard 7B Flagship
        return cls._cache.get("qwen2.5_coder_7b", cls._fallback_profile())

    @classmethod
    def _parse_yaml_file(cls, path: Path) -> Optional[AgentProfile]:
        """Parses an individual YAML agent spec file."""
        text = path.read_text(encoding="utf-8")
        data: Dict[str, Any] = {}

        if yaml:
            data = yaml.safe_load(text) or {}
        else:
            # Fallback simple parser if pyyaml is unavailable
            data = cls._simple_yaml_parse(text)

        metadata = data.get("metadata", {})
        spec = data.get("spec", {})

        return AgentProfile(
            id=metadata.get("id", path.stem),
            name=metadata.get("name", path.stem),
            tier=spec.get("tier", 1),
            context_window=spec.get("context_window", 32000),
            max_iterations=spec.get("max_iterations", 30),
            prompt_id=spec.get("prompt_id", "compact_7b_agent"),
            is_reasoning_model=spec.get("is_reasoning_model", False),
            strip_think_tags=spec.get("strip_think_tags", False),
            text_fallback_parser=spec.get("text_fallback_parser", True),
            whitelisted_tools=spec.get("whitelisted_tools", []),
            enabled_subagents=spec.get("enabled_subagents", []),
            target_models=spec.get("target_models", []),
        )

    @classmethod
    def _simple_yaml_parse(cls, text: str) -> Dict[str, Any]:
        """Minimal key-value fallback parser."""
        return {}

    @classmethod
    def _fallback_profile(cls) -> AgentProfile:
        """Built-in default profile if no YAML files exist."""
        return AgentProfile(
            id="qwen2.5_coder_7b",
            name="Qwen 2.5 Coder 7B Standard Flagship",
            tier=1,
            context_window=32000,
            max_iterations=30,
            whitelisted_tools=[
                "read_file", "write_file", "write_files", "edit_file",
                "insert_text", "list_directory", "lint_javascript",
                "get_assets", "ask_human", "finish", "execute_command",
                "run_background_command", "stop_background_command"
            ],
            enabled_subagents=["invoke_design_agent", "invoke_troubleshoot_agent"],
        )
