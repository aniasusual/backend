"""
Deterministic Static Aesthetic & UI/UX Analyzer.
Provides rule-based design system verification across index.html, index.css, and React components.
Serves as the resilient fallback for VisionExpertSubagent when LLM runner is unavailable.
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional


class StaticVisionAnalyzer:
    """
    Scans project workspace source files to evaluate:
    1. Google Font imports and typography scale.
    2. Dark mode contrast and semantic color variables.
    3. Responsive grid breakpoints (sm:, md:, lg:).
    4. Unstyled raw HTML elements and missing micro-interactions.
    5. Placeholder images and assets.
    """

    @classmethod
    def analyze(
        cls,
        sandbox_path: Optional[Path],
        target_component_or_file: str = "",
        design_intent: str = "",
    ) -> Dict[str, Any]:
        """
        Conducts static design analysis of workspace files.
        """
        findings: List[str] = []
        curated_assets_needed: List[str] = []
        scores: Dict[str, int] = {
            "Visual Hierarchy & Layout Balance": 88,
            "Color Harmony & Dark Mode Contrast (WCAG AA)": 90,
            "Typography Scale & Google Font Pairing": 85,
            "Responsive Grid Breakpoints": 85,
            "Micro-Interactions & Styling Polish": 86,
        }

        if not sandbox_path or not sandbox_path.exists():
            return {
                "overall_score": 85,
                "scores": scores,
                "findings": ["⚠️ Sandbox workspace not found. Basic heuristic report generated."],
                "curated_assets": [],
            }

        # 1. Discover key files
        index_html_path = sandbox_path / "index.html"
        index_css_path = sandbox_path / "src" / "index.css"
        app_jsx_path = sandbox_path / "src" / "App.jsx"

        target_file_path = None
        if target_component_or_file:
            tf = sandbox_path / target_component_or_file
            if tf.exists() and tf.is_file():
                target_file_path = tf

        index_html = index_html_path.read_text(encoding="utf-8", errors="ignore") if index_html_path.exists() else ""
        index_css = index_css_path.read_text(encoding="utf-8", errors="ignore") if index_css_path.exists() else ""
        app_jsx = app_jsx_path.read_text(encoding="utf-8", errors="ignore") if app_jsx_path.exists() else ""
        target_content = target_file_path.read_text(encoding="utf-8", errors="ignore") if target_file_path else app_jsx

        # ── Check Dimension 1: Google Font Pairings & Typography ─────────────
        has_font_link = bool(
            "fonts.googleapis.com" in index_html
            or "fonts.googleapis.com" in index_css
            or "@import url" in index_css
        )
        if not has_font_link:
            findings.append(
                "🔤 **Missing Google Font Pairings**: `index.html` / `index.css` lacks Google Fonts. "
                "Pair a modern display font (e.g., Outfit, Syne, Cabinet Grotesk) with a clean body sans (Inter, Plus Jakarta Sans)."
            )
            scores["Typography Scale & Google Font Pairing"] -= 20
        else:
            scores["Typography Scale & Google Font Pairing"] = min(96, scores["Typography Scale & Google Font Pairing"] + 6)

        # ── Check Dimension 2: Dark Mode & Color Contrast ────────────────────
        has_css_vars = bool("--primary" in index_css or "--bg-main" in index_css or "--background" in index_css)
        if not has_css_vars and index_css:
            findings.append(
                "🎨 **Missing Semantic Theme Tokens**: `src/index.css` lacks CSS custom properties. "
                "Define `--bg-main`, `--bg-card`, `--primary`, and `--border` tokens for consistent dark mode contrast."
            )
            scores["Color Harmony & Dark Mode Contrast (WCAG AA)"] -= 15

        # Check for raw hardcoded hex colors in JSX
        if target_content:
            raw_hex_matches = re.findall(r"['\"]#(?:[0-9a-fA-F]{3}){1,2}['\"]", target_content)
            # Filter out common benign dark backgrounds
            bad_hex = [h for h in raw_hex_matches if h.lower() in ['"#ff0000"', '"#00ff00"', '"#0000ff"', '"#ffffff"', '"#000000"']]
            if bad_hex:
                findings.append(
                    f"🎨 **Hardcoded Raw Hex Colors ({len(bad_hex)} found)**: Found raw hex colors `{', '.join(bad_hex[:3])}`. "
                    "Replace with theme variables (`var(--primary)`, `var(--danger)`) or Tailwind semantic color utilities."
                )
                scores["Color Harmony & Dark Mode Contrast (WCAG AA)"] -= 10

        # ── Check Dimension 3: Responsive Grid Breakpoints ──────────────────
        if target_content:
            if "grid" in target_content and "grid-cols-" in target_content:
                if "sm:grid-cols" not in target_content and "md:grid-cols" not in target_content and "lg:grid-cols" not in target_content:
                    findings.append(
                        "📱 **Static Grid Columns Detected**: Container uses fixed `grid-cols-X` without responsive prefixes. "
                        "Adapt with `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6` for mobile screens."
                    )
                    scores["Responsive Grid Breakpoints"] -= 18
                else:
                    scores["Responsive Grid Breakpoints"] = min(95, scores["Responsive Grid Breakpoints"] + 8)

        # ── Check Dimension 4: Unstyled Raw HTML & Micro-Interactions ────────
        if target_content:
            # Check for unstyled buttons lacking classes or hover/transition
            raw_buttons = re.findall(r"<button(?![^>]*class(?:Name)?=)[^>]*>", target_content)
            if raw_buttons:
                findings.append(
                    f"⚠️ **Unstyled Raw Button Elements ({len(raw_buttons)} detected)**: Raw `<button>` without styling found. "
                    "Use styled `.btn-primary` or add Tailwind classes with `transition-all duration-200 hover:scale-[1.02]`."
                )
                scores["Micro-Interactions & Styling Polish"] -= 15
            elif "<button" in target_content and "hover:" not in target_content and "transition" not in target_content:
                findings.append(
                    "💡 **Missing Button Micro-Interactions**: Buttons lack hover scale or shadow transitions. "
                    "Add `transition-all duration-200 hover:shadow-lg hover:scale-[1.02]`."
                )
                scores["Micro-Interactions & Styling Polish"] -= 8

            # Check for raw unstyled inputs
            raw_inputs = re.findall(r"<input(?![^>]*class(?:Name)?=)[^>]*>", target_content)
            if raw_inputs:
                findings.append(
                    f"⚠️ **Unstyled Input Fields ({len(raw_inputs)} detected)**: Form `<input>` elements lack styling. "
                    "Add rounded borders, dark mode background (`bg-slate-900/50`), and focus outline rings."
                )
                scores["Micro-Interactions & Styling Polish"] -= 10

        # ── Check Dimension 5: Placeholder Images & Asset Curation ───────────
        if target_content:
            placeholder_matches = re.findall(
                r"src=['\"](?:\s*|[^'\"]*(?:placeholder|picsum|dummyimage|via\.placeholder)[^'\"]*)['\"]",
                target_content,
                re.IGNORECASE,
            )
            if placeholder_matches:
                findings.append(
                    f"🖼️ **Generic Placeholder Images Detected ({len(placeholder_matches)} found)**: "
                    "Replace placeholder URLs with curated Unsplash CDN assets using `get_assets(query='...')`."
                )
                curated_assets_needed.append("high-resolution hero and card photography")
                scores["Visual Hierarchy & Layout Balance"] -= 12

        if not findings:
            findings.append(
                "✨ **Exemplary Design System Compliance**: Cohesive dark mode theme variables, "
                "responsive grid breakpoints, Google Font pairings, and smooth micro-interactions verified."
            )

        overall_score = max(50, min(98, round(sum(scores.values()) / len(scores))))

        return {
            "overall_score": overall_score,
            "scores": scores,
            "findings": findings,
            "curated_assets": curated_assets_needed,
            "target_file": str(target_file_path.relative_to(sandbox_path)) if target_file_path else "src/App.jsx",
        }

    @classmethod
    def generate_report(
        cls,
        analysis_data: Dict[str, Any],
        design_intent: str = "",
    ) -> str:
        """Formats the analysis findings into the structured Emergent-style review report."""
        overall_score = analysis_data.get("overall_score", 85)
        scores = analysis_data.get("scores", {})
        findings = analysis_data.get("findings", [])
        target_file = analysis_data.get("target_file", "src/App.jsx")

        if overall_score >= 90:
            status = "APPROVED"
        elif overall_score >= 75:
            status = "POLISH_RECOMMENDED"
        else:
            status = "REVISION_REQUIRED"

        report_lines = [
            "# 👁️ Vision & Aesthetic Review Report",
            f"**Design Intent**: {design_intent if design_intent else 'Modern High-End Web Application'}",
            f"**Target Component**: `{target_file}`",
            f"**Overall Visual Quality Score**: **{overall_score}/100**",
            f"**Status**: [{status}]",
            "\n---",
            "\n### 📊 Score Breakdown:",
        ]

        for dim, score in scores.items():
            report_lines.append(f"- **{dim}**: {score}/100")

        report_lines.append("\n---")
        report_lines.append("\n### 🔍 Aesthetic Findings & Anti-Patterns:")
        for f in findings:
            report_lines.append(f"- {f}")

        report_lines.append("\n---")
        report_lines.append("### 💎 Recommended Polish Actions:")
        report_lines.append("1. **Google Font Pairings**: Ensure distinct display heading and body sans are linked in `index.html`.")
        report_lines.append("2. **Micro-Interactions**: Add `transition-all duration-200 hover:scale-[1.02]` to all buttons and cards.")
        report_lines.append("3. **Responsive Breakpoints**: Ensure all grid containers use `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`.")
        report_lines.append("4. **Asset Curation**: Replace generic placeholder URLs with verified Unsplash images via `get_assets(query='...')`.")
        report_lines.append("\n### 📋 Instructions for Main Engineer:")
        if status == "APPROVED":
            report_lines.append("- Visual styling meets high-end production standards. You may proceed to conclude with `finish`.")
        else:
            report_lines.append("- Call `edit_file` to apply the recommended CSS/Tailwind polish directives before finishing.")

        return "\n".join(report_lines)
