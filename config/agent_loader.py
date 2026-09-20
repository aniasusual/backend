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
    "locate_files_by_pattern",
    "extract_signatures",
    "map_dependencies",
    "mount_file",
    "unmount_file",
    "close_file",
    "list_mounted_files",
    "lint_javascript",
    "get_assets",
    "search_web",
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
    "invoke_testing_agent",
    "invoke_code_reviewer_agent",
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
    max_iterations: int = 100
    prompt_id: str = "master_agent"
    is_reasoning_model: bool = False
    strip_think_tags: bool = False
    text_fallback_parser: bool = True
    supports_native_tools: bool = True
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
        Resolves a model name (e.g. 'qwen2.5-coder:14b', 'deepseek-coder-v2:16b', 'qwen3-coder:30b-a3b')
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

        # 2. Pattern Matching Heuristics for supported models
        # DeepSeek-Coder-V2-Lite
        if "deepseek" in clean_name:
            if "deepseek_coder_v2_lite" in cls._cache:
                return cls._cache["deepseek_coder_v2_lite"]

        # Meta Muse-Glimmer-30B
        if "glimmer" in clean_name or "muse" in clean_name:
            if "muse_glimmer_30b" in cls._cache:
                return cls._cache["muse_glimmer_30b"]

        # Qwen3-Coder-30B-A3B
        if "qwen3" in clean_name or "30b" in clean_name or "a3b" in clean_name:
            if "qwen3_coder_30b" in cls._cache:
                return cls._cache["qwen3_coder_30b"]

        # Qwen 2.5 Coder 7B
        if "7b" in clean_name:
            if "qwen2.5_coder_7b" in cls._cache:
                return cls._cache["qwen2.5_coder_7b"]

        # Qwen 2.5 Coder 14B
        if "14b" in clean_name or "qwen2.5" in clean_name or "qwen" in clean_name:
            if "qwen2.5_coder_14b" in cls._cache:
                return cls._cache["qwen2.5_coder_14b"]

        # Default fallback: Qwen 2.5 Coder 14B Flagship
        return cls._cache.get("qwen2.5_coder_14b", cls._fallback_profile())

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

        whitelisted = spec.get("whitelisted_tools")
        if not whitelisted:
            whitelisted = list(ALL_STANDARD_TOOLS)

        subagents = spec.get("enabled_subagents")
        if subagents is None:
            subagents = list(ALL_SUBAGENTS)

        return AgentProfile(
            id=metadata.get("id", path.stem),
            name=metadata.get("name", path.stem),
            tier=spec.get("tier", 1),
            context_window=spec.get("context_window", 32000),
            max_iterations=spec.get("max_iterations", 100),
            prompt_id=spec.get("prompt_id", "intermediate_14b_agent"),
            is_reasoning_model=spec.get("is_reasoning_model", False),
            strip_think_tags=spec.get("strip_think_tags", False),
            text_fallback_parser=spec.get("text_fallback_parser", True),
            supports_native_tools=spec.get("supports_native_tools", True),
            whitelisted_tools=whitelisted,
            enabled_subagents=subagents,
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
            id="qwen2.5_coder_14b",
            name="Qwen 2.5 Coder 14B Flagship Agent",
            tier=2,
            context_window=32768,
            max_iterations=100,
            prompt_id="intermediate_14b_agent",
            whitelisted_tools=list(ALL_STANDARD_TOOLS),
            enabled_subagents=list(ALL_SUBAGENTS),
            target_models=["qwen2.5-coder:14b", "qwen2.5-coder:14b-instruct"],
        )
