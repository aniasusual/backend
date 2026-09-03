"""
Curated Model Catalog and Hardware Compatibility Engine for Lowkey.

Maintains metadata for best-in-class local coding models and computes
real-time hardware compatibility scores based on system RAM and architecture.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Any, List, Optional

DEFAULT_MODEL_ID = os.getenv("DEFAULT_MODEL_ID", "qwen2.5-coder:7b")

CURATED_MODELS: List[Dict[str, Any]] = [
    # ---- Ultra-Lightweight (4 GB – 8 GB RAM) ----
    {
        "id": "qwen2.5-coder:1.5b",
        "name": "Qwen 2.5 Coder 1.5B",
        "param_size": "1.5B",
        "required_ram_gb": 2.0,
        "context_length": "32k",
        "description": "Ultra-lightweight and blazingly fast. Ideal for low-spec or portable laptops.",
        "tags": ["Ultra-Fast", "Low Memory"],
        "is_default": False,
    },
    {
        "id": "qwen2.5-coder:3b",
        "name": "Qwen 2.5 Coder 3B",
        "param_size": "3.1B",
        "required_ram_gb": 3.5,
        "context_length": "32k",
        "description": "Fast and capable coder with the ideal balance for 8 GB RAM machines.",
        "tags": ["Fast", "8GB Optimized"],
        "is_default": False,
    },
    {
        "id": "llama3.2:3b",
        "name": "Llama 3.2 3B",
        "param_size": "3.2B",
        "required_ram_gb": 3.5,
        "context_length": "128k",
        "description": "Meta's ultra-fast compact generalist with an expansive 128k context window.",
        "tags": ["128k Context", "Compact"],
        "is_default": False,
    },

    # ---- Standard & High-Efficiency (8 GB – 16 GB RAM) ----
    {
        "id": "qwen2.5-coder:7b",
        "name": "Qwen 2.5 Coder 7B",
        "param_size": "7.6B",
        "required_ram_gb": 5.0,
        "context_length": "32k",
        "description": "Balanced speed & accuracy with native tool support. Ideal for full-stack apps.",
        "tags": ["Fast", "Native Tools", "Full-Stack"],
        "is_default": True,
    },
    {
        "id": "llama3.1:8b",
        "name": "Llama 3.1 8B",
        "param_size": "8.0B",
        "required_ram_gb": 5.5,
        "context_length": "128k",
        "description": "Meta's flagship open generalist model with a massive 128k context window.",
        "tags": ["128k Context", "Meta"],
        "is_default": False,
    },
    {
        "id": "deepseek-r1:7b",
        "name": "DeepSeek R1 7B",
        "param_size": "7.6B",
        "required_ram_gb": 5.0,
        "context_length": "64k",
        "description": "Lightweight step-by-step reasoning specialist (Qwen-distilled).",
        "tags": ["Reasoning", "Chain-of-Thought"],
        "is_default": False,
    },
    {
        "id": "deepseek-r1:8b",
        "name": "DeepSeek R1 8B",
        "param_size": "8.0B",
        "required_ram_gb": 5.5,
        "context_length": "64k",
        "description": "Llama-distilled reasoning model featuring step-by-step thinking.",
        "tags": ["Reasoning", "Llama-Distill"],
        "is_default": False,
    },
    {
        "id": "gemma2:9b",
        "name": "Gemma 2 9B",
        "param_size": "9.2B",
        "required_ram_gb": 6.5,
        "context_length": "8k",
        "description": "Google DeepMind's high-efficiency architecture with strong code comprehension.",
        "tags": ["Google", "Efficient"],
        "is_default": False,
    },

    # ---- Medium & Heavyweight (16 GB – 32 GB RAM) ----
    {
        "id": "mistral-nemo:12b",
        "name": "Mistral Nemo 12B",
        "param_size": "12.2B",
        "required_ram_gb": 8.5,
        "context_length": "128k",
        "description": "Mistral AI & NVIDIA collaboration with 128k context and robust code logic.",
        "tags": ["128k Context", "Mistral"],
        "is_default": False,
    },
    {
        "id": "deepseek-coder-v2:16b",
        "name": "DeepSeek Coder V2 16B",
        "param_size": "16B (MoE)",
        "required_ram_gb": 9.5,
        "context_length": "128k",
        "description": "Mixture-of-Experts coding model with 2.4B active parameters and 128k context.",
        "tags": ["MoE", "128k Context", "Multi-File"],
        "is_default": False,
    },
    {
        "id": "qwen2.5-coder:14b",
        "name": "Qwen 2.5 Coder 14B",
        "param_size": "14.7B",
        "required_ram_gb": 10.0,
        "context_length": "32k",
        "description": "High-accuracy reasoning and architectural planning across multi-file features.",
        "tags": ["Deep Reasoning", "Architecture"],
        "is_default": False,
    },
    {
        "id": "deepseek-r1:14b",
        "name": "DeepSeek R1 14B",
        "param_size": "14.7B",
        "required_ram_gb": 10.0,
        "context_length": "64k",
        "description": "Reasoning specialist with deep step-by-step thinking for intricate algorithms.",
        "tags": ["Reasoning", "Math/Logic"],
        "is_default": False,
    },
    {
        "id": "codestral:22b",
        "name": "Codestral 22B",
        "param_size": "22.2B",
        "required_ram_gb": 14.5,
        "context_length": "32k",
        "description": "Mistral AI's dedicated flagship model engineered explicitly for code generation.",
        "tags": ["Mistral", "SOTA Code"],
        "is_default": False,
    },
    {
        "id": "gemma2:27b",
        "name": "Gemma 2 27B",
        "param_size": "27.2B",
        "required_ram_gb": 18.0,
        "context_length": "8k",
        "description": "Google DeepMind's compact powerhouse for advanced reasoning and refactoring.",
        "tags": ["Google", "Powerhouse"],
        "is_default": False,
    },

    # ---- Flagship & Workstation (32 GB – 128 GB RAM) ----
    {
        "id": "qwen2.5-coder:32b",
        "name": "Qwen 2.5 Coder 32B",
        "param_size": "32.5B",
        "required_ram_gb": 22.0,
        "context_length": "32k",
        "description": "Flagship open coding model with expert-level multi-file generation and refactoring.",
        "tags": ["State of the Art", "Expert"],
        "is_default": False,
    },
    {
        "id": "deepseek-r1:32b",
        "name": "DeepSeek R1 32B",
        "param_size": "32.5B",
        "required_ram_gb": 22.0,
        "context_length": "64k",
        "description": "Flagship open reasoning model for complex fullstack architectures.",
        "tags": ["Reasoning", "Flagship"],
        "is_default": False,
    },
    {
        "id": "llama3.3:70b",
        "name": "Llama 3.3 70B",
        "param_size": "70.6B",
        "required_ram_gb": 45.0,
        "context_length": "128k",
        "description": "Meta's premier flagship generalist model with unmatched open intelligence.",
        "tags": ["Meta", "Flagship 70B", "128k Context"],
        "is_default": False,
    },
    {
        "id": "deepseek-r1:70b",
        "name": "DeepSeek R1 70B",
        "param_size": "70.6B",
        "required_ram_gb": 45.0,
        "context_length": "64k",
        "description": "State-of-the-art chain-of-thought reasoning powerhouse for high-end workstations.",
        "tags": ["SOTA Reasoning", "Workstation"],
        "is_default": False,
    },
]



def get_model_context_window(model_id: str, default: int = 32768) -> int:
    """Returns the context window token limit for a model ID."""
    clean_id = model_id.split(":")[0] if ":" in model_id else model_id
    for m in CURATED_MODELS:
        if m["id"] == model_id or m["id"].startswith(clean_id):
            ctx_str = str(m.get("context_length", "32k")).lower().strip()
            if ctx_str.endswith("k"):
                try:
                    return int(ctx_str[:-1]) * 1024
                except ValueError:
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
            return 10.5
        elif params_b <= 35.0:
            return 22.0
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
    Combines curated models with installed Ollama models and attaches
    hardware compatibility evaluations.
    """
    # Map installed models by normalized name / tag
    installed_map: Dict[str, Dict[str, Any]] = {}
    for item in installed_tags:
        name = item.get("name") or item.get("model") or ""
        if name:
            installed_map[name] = item
            # Also map without ':latest' if applicable
            if name.endswith(":latest"):
                installed_map[name[:-7]] = item

    catalog: List[Dict[str, Any]] = []
    seen_ids = set()

    # 1. Process Curated Models
    for cm in CURATED_MODELS:
        m_id = cm["id"]
        seen_ids.add(m_id)

        # Check if installed
        is_installed = m_id in installed_map or f"{m_id}:latest" in installed_map
        installed_info = installed_map.get(m_id) or installed_map.get(f"{m_id}:latest") or {}

        compat = evaluate_compatibility(cm["required_ram_gb"], hardware_info)

        catalog.append({
            **cm,
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

    # 2. Add any custom installed models in Ollama that were not in curated list
    for name, info in installed_map.items():
        if name in seen_ids or f"{name}:latest" in seen_ids:
            continue
        # Avoid duplicate entries for ':latest' aliases
        base_name = name[:-7] if name.endswith(":latest") else name
        if base_name in seen_ids:
            continue

        seen_ids.add(name)
        seen_ids.add(base_name)

        details = info.get("details", {})
        param_size = details.get("parameter_size", "Unknown")
        req_ram = estimate_required_ram(param_size, default=6.0)
        compat = evaluate_compatibility(req_ram, hardware_info)

        catalog.append({
            "id": name,
            "name": name,
            "param_size": param_size,
            "required_ram_gb": req_ram,
            "context_length": str(details.get("context_length", "32k")),
            "description": f"Locally installed Ollama model ({param_size}).",
            "tags": ["Custom Local"],
            "is_default": False,
            "installed": True,
            "installed_size_bytes": info.get("size", 0),
            "modified_at": info.get("modified_at"),
            "compatibility": compat["tier"],
            "compatibility_badge": compat["badge"],
            "compatibility_label": compat["label"],
            "compatibility_reason": compat["reason"],
            "can_run": compat["can_run"],
            "is_curated": False,
        })

    return catalog
