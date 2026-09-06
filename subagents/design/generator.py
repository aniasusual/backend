"""
Dynamic CSS Design System Generator & Styling Framework Detector.
Detects and strictly preserves Tailwind CSS directives while generating bespoke design tokens.
Dynamically parses user color and mood preferences for resilient fallback styling.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


def detect_tailwind(sandbox_path: Optional[Path]) -> Tuple[bool, str]:
    """
    Inspects project files to detect if Tailwind CSS is used.
    Returns (is_tailwind, existing_index_css_content).
    """
    if not sandbox_path or not sandbox_path.exists():
        return False, ""

    existing_css = ""
    css_file = sandbox_path / "src" / "index.css"
    if css_file.exists():
        try:
            existing_css = css_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            existing_css = ""

    # Check 1: Existing index.css contains @tailwind or @import "tailwindcss"
    if "@tailwind" in existing_css or '@import "tailwindcss"' in existing_css or "@import 'tailwindcss'" in existing_css:
        return True, existing_css

    # Check 2: package.json dependencies contain tailwindcss
    pkg_file = sandbox_path / "package.json"
    if pkg_file.exists():
        try:
            pkg_data = json.loads(pkg_file.read_text(encoding="utf-8", errors="ignore"))
            deps = pkg_data.get("dependencies", {})
            dev_deps = pkg_data.get("devDependencies", {})
            if "tailwindcss" in deps or "tailwindcss" in dev_deps:
                return True, existing_css
        except Exception:
            pass

    # Check 3: tailwind.config.js / tailwind.config.ts exists
    if (sandbox_path / "tailwind.config.js").exists() or (sandbox_path / "tailwind.config.ts").exists():
        return True, existing_css

    return False, existing_css


def parse_user_taste(problem_statement: str, theme_preference: str = "") -> Dict[str, Any]:
    """
    Dynamically extracts color cues, mood, and aesthetic requirements from user text.
    Synthesizes custom palette tokens and font pairings matching the user's explicit taste.
    """
    combined = f"{theme_preference} {problem_statement}".lower()

    # Dynamic Color Mood Mapping based on user cues
    if any(k in combined for k in ["terracotta", "warm", "amber", "sunset", "orange", "clay"]):
        primary = "#f97316"
        primary_hover = "#ea580c"
        accent = "#f59e0b"
        bg_main = "#140e0b"
        name = "Warm Terracotta & Sunset Glow"
        font_h = "Outfit, sans-serif"
        font_url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700;800&display=swap"
    elif any(k in combined for k in ["emerald", "green", "sage", "forest", "nature", "mint", "eco"]):
        primary = "#10b981"
        primary_hover = "#059669"
        accent = "#34d399"
        bg_main = "#091410"
        name = "Emerald & Deep Botanical Slate"
        font_h = "Plus Jakarta Sans, sans-serif"
        font_url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap"
    elif any(k in combined for k in ["violet", "neon", "cyber", "purple", "fuchsia", "gaming"]):
        primary = "#8b5cf6"
        primary_hover = "#7c3aed"
        accent = "#ec4899"
        bg_main = "#0d0914"
        name = "Neon Violet Cyberpunk"
        font_h = "Outfit, sans-serif"
        font_url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700;800&display=swap"
    elif any(k in combined for k in ["rose", "pink", "coral", "pastel", "candy"]):
        primary = "#f43f5e"
        primary_hover = "#e11d48"
        accent = "#fb7185"
        bg_main = "#140b0e"
        name = "Electric Rose & Soft Coral"
        font_h = "Plus Jakarta Sans, sans-serif"
        font_url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap"
    elif any(k in combined for k in ["gold", "luxury", "champagne", "bronze", "estate"]):
        primary = "#d97706"
        primary_hover = "#b45309"
        accent = "#f59e0b"
        bg_main = "#141109"
        name = "Champagne Gold & Obsidian"
        font_h = "Plus Jakarta Sans, sans-serif"
        font_url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap"
    elif any(k in combined for k in ["terminal", "matrix", "hacker", "code", "dev"]):
        primary = "#22c55e"
        primary_hover = "#16a34a"
        accent = "#4ade80"
        bg_main = "#070c08"
        name = "Obsidian Terminal Matrix"
        font_h = "Inter, sans-serif"
        font_url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    elif any(k in combined for k in ["cyan", "teal", "aqua", "ocean"]):
        primary = "#06b6d4"
        primary_hover = "#0891b2"
        accent = "#38bdf8"
        bg_main = "#081116"
        name = "Deep Oceanic Cyan"
        font_h = "Outfit, sans-serif"
        font_url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700;800&display=swap"
    else:
        # Default to high-end Linear/Vercel sleek midnight indigo
        primary = "#6366f1"
        primary_hover = "#4f46e5"
        accent = "#06b6d4"
        bg_main = "#090d16"
        name = "Sleek Midnight Slate & Electric Indigo"
        font_h = "Outfit, sans-serif"
        font_url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700;800&display=swap"

    return {
        "name": name,
        "primary": primary,
        "primary_hover": primary_hover,
        "accent": accent,
        "bg_main": bg_main,
        "font_heading": font_h,
        "font_url": font_url,
    }


def generate_design_system_css(
    theme: Dict[str, Any],
    is_tailwind: bool = False,
    existing_css: str = "",
) -> str:
    """
    Generates cohesive CSS design tokens.
    If Tailwind is detected, strictly preserves @tailwind directives and wraps utilities in @layer components.
    """
    name = theme["name"]
    primary = theme["primary"]
    primary_hover = theme["primary_hover"]
    accent = theme["accent"]
    bg_main = theme["bg_main"]
    font_h = theme["font_heading"]
    font_url = theme["font_url"]

    # Base variables block
    vars_block = f"""/* LOWKEY BESPOKE DESIGN SYSTEM — {name} */
@import url('{font_url}');

:root {{
  font-family: Inter, sans-serif;
  color-scheme: dark;
  --bg-main: {bg_main};
  --bg-surface: rgba(17, 24, 39, 0.75);
  --bg-card: rgba(30, 41, 59, 0.55);
  --bg-card-hover: rgba(51, 65, 85, 0.65);
  --border-subtle: rgba(255, 255, 255, 0.08);
  --border-glow: {primary}55;
  --primary: {primary};
  --primary-hover: {primary_hover};
  --primary-glow: {primary}40;
  --accent: {accent};
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --glass-blur: 16px;
  --radius-sm: 8px;
  --radius-md: 12px;
  --shadow-card: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
  --shadow-glow: 0 0 25px {primary}4d;
}}

body {{
  background-color: var(--bg-main);
  color: var(--text-primary);
  font-family: Inter, sans-serif;
  min-height: 100vh;
}}

h1, h2, h3, h4 {{ font-family: {font_h}; font-weight: 700; }}
"""

    custom_utilities = f"""
.glass-panel {{
  background: var(--bg-surface);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}}
.glass-card {{
  background: var(--bg-card);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  transition: all 0.25s ease;
}}
.glass-card:hover {{
  background: var(--bg-card-hover);
  border-color: var(--border-glow);
  transform: translateY(-2px);
  box-shadow: var(--shadow-glow);
}}
.btn-primary {{
  background: var(--primary);
  color: #fff;
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-sm);
  font-weight: 600;
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s ease;
}}
.btn-primary:hover {{ background: var(--primary-hover); transform: translateY(-1px); }}
.btn-secondary {{
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: all 0.2s ease;
}}
.btn-secondary:hover {{ border-color: var(--primary); }}
.badge {{
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.625rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  border: 1px solid var(--border-subtle);
}}
input, textarea, select {{
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  padding: 0.625rem 0.875rem;
  font-family: inherit;
  width: 100%;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}}
input:focus, textarea:focus, select:focus {{
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-glow);
}}
"""

    if is_tailwind:
        # Preserve Tailwind directives at the absolute top
        tailwind_header = "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n"
        return f"{tailwind_header}{vars_block}\n@layer components {{{custom_utilities}\n}}\n"
    else:
        reset_block = "* { box-sizing: border-box; margin: 0; padding: 0; }\n"
        return f"{vars_block}\n{reset_block}{custom_utilities}\n"
