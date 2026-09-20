"""
Verification script for all 4 curated models in Lowkey:
1. Qwen 2.5 Coder 14B (Flagship Default)
2. DeepSeek-Coder-V2-Lite (16B, 2.4B active)
3. Qwen3-Coder-30B-A3B (MoE 30B)
4. Meta Muse Glimmer 30B (Dense 30B Multimodal Agentic)
"""

import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from config.models import (
    DEFAULT_MODEL_ID,
    CURATED_MODELS,
    build_model_catalog,
    get_model_context_window,
)
from config.agent_loader import AgentLoader

def test_models():
    print(f"DEFAULT_MODEL_ID: {DEFAULT_MODEL_ID}")
    assert DEFAULT_MODEL_ID == "qwen2.5-coder:14b", "Default model ID must be qwen2.5-coder:14b"

    print(f"Total curated models: {len(CURATED_MODELS)}")
    assert len(CURATED_MODELS) == 4, f"Expected 4 curated models, got {len(CURATED_MODELS)}"

    model_ids = [m["id"] for m in CURATED_MODELS]
    print(f"Curated Model IDs: {model_ids}")
    assert "qwen2.5-coder:14b" in model_ids
    assert "deepseek-coder-v2:16b" in model_ids
    assert "qwen3-coder:30b-a3b" in model_ids
    assert "muse-glimmer:30b" in model_ids

    # Check context windows
    assert get_model_context_window("qwen2.5-coder:14b") == 32768
    assert get_model_context_window("deepseek-coder-v2:16b") == 131072
    assert get_model_context_window("qwen3-coder:30b-a3b") == 262144
    assert get_model_context_window("qwen3-coder:30b") == 262144
    assert get_model_context_window("muse-glimmer:30b") == 131072
    assert get_model_context_window("muse-glimmer") == 131072
    assert get_model_context_window("muse-glimmer:30b-q4_K_M") == 131072

    # Test catalog building with mock installed tags (including uncurated models that should NOT leak)
    mock_installed = [
        {"name": "qwen2.5-coder:14b", "size": 9000000000},
        {"name": "deepseek-r1:14b", "size": 9000000000},  # should NOT be in catalog
        {"name": "qwen2.5-coder:7b", "size": 4700000000},  # should NOT be in catalog
    ]
    mock_hw = {"total_ram_gb": 16.0}
    catalog = build_model_catalog(mock_installed, mock_hw)

    print(f"Catalog items count: {len(catalog)}")
    assert len(catalog) == 4, f"Catalog must strictly have 4 items, got {len(catalog)}"

    catalog_ids = [m["id"] for m in catalog]
    assert "deepseek-r1:14b" not in catalog_ids, "Uncurated models must not leak into catalog"
    assert "qwen2.5-coder:7b" not in catalog_ids, "Removed models must not leak into catalog"

    qwen14 = next(m for m in catalog if m["id"] == "qwen2.5-coder:14b")
    assert qwen14["installed"] is True, "qwen2.5-coder:14b should be detected as installed"

    muse = next(m for m in catalog if m["id"] == "muse-glimmer:30b")
    assert muse["installed"] is False, "muse-glimmer:30b should be detected as not installed"
    assert muse["compatibility"] == "insufficient", "19.5GB model on 16GB RAM should be flagged as insufficient"
    print(f"Muse Glimmer catalog entry: {muse['name']}, RAM: {muse['required_ram_gb']}GB, Context: {muse['context_length']}, Badge: {muse['compatibility_badge']}")

    # Test AgentLoader resolution
    profiles = AgentLoader.load_all_profiles()
    print(f"Loaded profiles: {list(profiles.keys())}")
    assert "qwen2.5_coder_14b" in profiles
    assert "deepseek_coder_v2_lite" in profiles
    assert "qwen3_coder_30b" in profiles
    assert "muse_glimmer_30b" in profiles

    p1 = AgentLoader.get_profile_for_model("qwen2.5-coder:14b")
    assert p1.id == "qwen2.5_coder_14b", f"Expected qwen2.5_coder_14b, got {p1.id}"

    p2 = AgentLoader.get_profile_for_model("deepseek-coder-v2:16b")
    assert p2.id == "deepseek_coder_v2_lite", f"Expected deepseek_coder_v2_lite, got {p2.id}"

    p3 = AgentLoader.get_profile_for_model("qwen3-coder:30b-a3b")
    assert p3.id == "qwen3_coder_30b", f"Expected qwen3_coder_30b, got {p3.id}"

    p3_alias = AgentLoader.get_profile_for_model("qwen3-coder:30b")
    assert p3_alias.id == "qwen3_coder_30b", f"Expected qwen3_coder_30b, got {p3_alias.id}"

    p4 = AgentLoader.get_profile_for_model("muse-glimmer:30b")
    assert p4.id == "muse_glimmer_30b", f"Expected muse_glimmer_30b, got {p4.id}"

    p4_alias1 = AgentLoader.get_profile_for_model("muse-glimmer")
    assert p4_alias1.id == "muse_glimmer_30b", f"Expected muse_glimmer_30b, got {p4_alias1.id}"

    p4_alias2 = AgentLoader.get_profile_for_model("muse-glimmer:30b-q4_k_m")
    assert p4_alias2.id == "muse_glimmer_30b", f"Expected muse_glimmer_30b, got {p4_alias2.id}"

    p4_heuristic = AgentLoader.get_profile_for_model("custom-glimmer-fine-tune")
    assert p4_heuristic.id == "muse_glimmer_30b", f"Expected muse_glimmer_30b, got {p4_heuristic.id}"

    assert p4.context_window == 131072, f"Expected 131072 context window, got {p4.context_window}"
    assert "invoke_vision_agent" in p4.enabled_subagents, "invoke_vision_agent must be enabled for Muse Glimmer"
    assert "read_file" in p4.whitelisted_tools, "read_file must be whitelisted"

    fallback = AgentLoader.get_profile_for_model("nonexistent-model")
    assert fallback.id == "qwen2.5_coder_14b", f"Fallback should be qwen2.5_coder_14b, got {fallback.id}"

    print("\nALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_models()
