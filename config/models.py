"""
Curated Model Catalog and Hardware Compatibility Engine for Lowkey.

Maintains metadata for best-in-class local coding models and computes
real-time hardware compatibility scores based on system RAM and architecture.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Any, List, Optional

DEFAULT_MODEL_ID = os.getenv("DEFAULT_MODEL_ID", "qwen2.5-coder:14b")

CURATED_MODELS: List[Dict[str, Any]] = [
    {
        "id": "qwen2.5-coder:7b",
        "name": "Qwen 2.5 Coder 7B",
        "param_size": "7.6B",
        "required_ram_gb": 5.0,
        "context_length": "32k",
        "description": "Ultra-fast code generation and agentic tool use optimized for local 16GB machines (60-80+ tok/s).",
        "tags": ["Fast & Lightweight", "Native Tools", "Optimal Performance", "SOTA 7B"],
        "is_default": False,
        "aliases": [
            "qwen2.5-coder:7b",
            "qwen2.5-coder:7b-instruct",
            "qwen2.5-coder:latest",
            "qwen2.5-coder:7b-instruct-q4_K_M",
            "qwen2.5-coder",
        ],
    },
    {
        "id": "qwen2.5-coder:14b",
        "name": "Qwen 2.5 Coder 14B",
        "param_size": "14.7B",
        "required_ram_gb": 10.0,
        "context_length": "32k",
        "description": "High-accuracy reasoning and architectural planning across multi-file features with native tool calling.",
        "tags": ["Flagship Default", "Native Tools", "Full-Stack"],
        "is_default": True,
        "aliases": ["qwen2.5-coder:14b", "qwen2.5-coder:14b-instruct", "qwen2.5-coder:14b-instruct-q4_K_M"],
    },
    {
        "id": "deepseek-coder-v2:16b",
        "name": "DeepSeek-Coder-V2-Lite (16B, 2.4B active)",
        "param_size": "16B (2.4B active)",
        "required_ram_gb": 9.5,
        "context_length": "128k",
        "description": "Mixture-of-Experts coding model with 2.4B active parameters and 128k context for repository-scale code synthesis.",
        "tags": ["MoE", "128k Context", "Multi-File", "Code Specialist"],
        "is_default": False,
        "aliases": ["deepseek-coder-v2:16b", "deepseek-coder-v2-lite:16b", "deepseek-coder-v2-lite", "deepseek-coder-v2:16b-lite"],
    },
    {
        "id": "qwen3-coder:30b-a3b",
        "name": "Qwen3-Coder-30B-A3B",
        "param_size": "30.5B (3.3B active)",
        "required_ram_gb": 18.5,
        "context_length": "256k",
        "description": "Next-generation Mixture-of-Experts agentic coding model with 3.3B active parameters, 256k context, and native tool execution.",
        "tags": ["MoE", "256k Context", "Agentic", "SOTA Code"],
        "is_default": False,
        "aliases": ["qwen3-coder:30b-a3b", "qwen3-coder:30b", "qwen3-coder:30b-a3b-instruct", "qwen3-coder:30b-instruct"],
    },
    {
        "id": "muse-glimmer:30b",
        "name": "Meta Muse Glimmer 30B",
        "param_size": "30B (Dense Multimodal)",
        "required_ram_gb": 19.5,
        "context_length": "128k",
        "description": "Meta 30B dense multimodal agentic model with built-in tool failure recovery, controllable reasoning, and 2B vision encoder.",
        "tags": ["Dense 30B", "Multimodal", "Agentic", "Failure Recovery", "SOTA Tools"],
        "is_default": False,
        "aliases": [
            "muse-glimmer:30b",
            "muse-glimmer",
            "muse-glimmer:latest",
            "muse-glimmer:30b-q4_K_M",
            "muse-glimmer:30b-instruct",
            "muse-glimmer-30b",
        ],
    },
]


def get_model_context_window(model_id: str, default: int = 32768) -> int:
    """Returns the context window token limit for a model ID."""
    clean_id = (model_id or "").lower().strip()
    clean_base = clean_id.split(":")[0] if ":" in clean_id else clean_id

    # 1. Exact match or alias match
    for m in CURATED_MODELS:
        m_id = m["id"].lower()
        aliases = [a.lower() for a in m.get("aliases", [])]
        if clean_id == m_id or clean_id in aliases:
            ctx_str = str(m.get("context_length", "32k")).lower().strip()
            if ctx_str.endswith("k"):
                try:
                    return int(ctx_str[:-1]) * 1024
                except ValueError:
                    pass

    # 2. Specific prefix match for tags/quantizations (e.g. qwen2.5-coder:14b-instruct-q4_K_M)
    for m in CURATED_MODELS:
        m_id = m["id"].lower()
        aliases = [a.lower() for a in m.get("aliases", [])]
        if clean_id.startswith(m_id) or any(clean_id.startswith(a) for a in aliases):
            ctx_str = str(m.get("context_length", "32k")).lower().strip()
            if ctx_str.endswith("k"):
                try:
                    return int(ctx_str[:-1]) * 1024
                except ValueError:
                    pass

    # 3. Base prefix match fallback (e.g. if passed without tag)
    for m in CURATED_MODELS:
        m_id = m["id"].lower()
        aliases = [a.lower() for a in m.get("aliases", [])]
        if m_id.startswith(clean_base) or any(a.startswith(clean_base) for a in aliases):
            ctx_str = str(m.get("context_length", "32k")).lower().strip()
            if ctx_str.endswith("k"):
                try:
                    return int(ctx_str[:-1]) * 1024
                except ValueError:
                    pass

    # 4. Agent profile fallback (if configured in agent YAML specs)
    try:
        from config.agent_loader import AgentLoader
        profile = AgentLoader.get_profile_for_model(clean_id)
        if profile and hasattr(profile, "context_window") and profile.context_window:
            if profile.id != "qwen2.5_coder_14b" or clean_base.startswith("qwen2.5-coder:14b"):
                return profile.context_window
    except Exception:
        pass

    return default


def estimate_required_ram(param_str: str, default: float = 5.0) -> float:
    """Estimates required RAM in GB from parameter size string (e.g. '7B', '14B')."""
    match = re.search(r"(\d+(\.\d+)?)\s*B", param_str, re.IGNORECASE)
    if match:
        params_b = float(match.group(1))
        if params_b <= 2.0:
            return 2.0
        elif params_b <= 4.0:
            return 3.5
        elif params_b <= 9.0:
            return 5.5
        elif params_b <= 16.0:
            return 10.0
        elif params_b <= 35.0:
            return 18.5
        elif params_b <= 75.0:
            return 45.0
        else:
            return round(params_b * 0.7, 1)
    return default


def evaluate_compatibility(required_ram_gb: float, hardware_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes compatibility tier and explanatory label for a given RAM requirement.
    """
    total_ram = float(hardware_info.get("total_ram_gb", 8.0))

    if required_ram_gb <= total_ram * 0.55:
        return {
            "tier": "optimal",
            "badge": "Optimal",
            "label": "Optimal",
            "reason": f"Comfortably fits in {total_ram} GB RAM ({required_ram_gb} GB needed)",
            "can_run": True,
        }
    elif required_ram_gb <= total_ram * 0.82:
        return {
            "tier": "usable",
            "badge": "Usable",
            "label": "Usable",
            "reason": f"Runs well, uses {required_ram_gb} GB of {total_ram} GB RAM",
            "can_run": True,
        }
    else:
        min_recommended = max(16, int(required_ram_gb * 1.35))
        return {
            "tier": "insufficient",
            "badge": f"Requires {min_recommended}GB+ RAM",
            "label": "Insufficient RAM",
            "reason": f"Requires {min_recommended} GB+ system RAM ({total_ram} GB available)",
            "can_run": False,
        }


def build_model_catalog(
    installed_tags: List[Dict[str, Any]],
    hardware_info: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Combines the supported curated models with installed Ollama tags and attaches
    hardware compatibility evaluations.
    """
    # Map installed models by normalized name / tag
    installed_map: Dict[str, Dict[str, Any]] = {}
    for item in installed_tags:
        name = (item.get("name") or item.get("model") or "").lower()
        if name:
            installed_map[name] = item
            if name.endswith(":latest"):
                installed_map[name[:-7]] = item

    catalog: List[Dict[str, Any]] = []

    for cm in CURATED_MODELS:
        m_id = cm["id"]
        aliases = [a.lower() for a in cm.get("aliases", [])]
        all_match_keys = [m_id.lower(), f"{m_id.lower()}:latest"] + aliases + [f"{a}:latest" for a in aliases]

        is_installed = False
        installed_info: Dict[str, Any] = {}
        for key in all_match_keys:
            if key in installed_map:
                is_installed = True
                installed_info = installed_map[key]
                break

        compat = evaluate_compatibility(cm["required_ram_gb"], hardware_info)

        catalog_entry = {k: v for k, v in cm.items() if k != "aliases"}
        catalog_entry.update({
            "installed": is_installed,
            "installed_size_bytes": installed_info.get("size", 0),
            "modified_at": installed_info.get("modified_at"),
            "compatibility": compat["tier"],
            "compatibility_badge": compat["badge"],
            "compatibility_label": compat["label"],
            "compatibility_reason": compat["reason"],
            "can_run": compat["can_run"],
            "is_curated": True,
        })
        catalog.append(catalog_entry)

    return catalog
