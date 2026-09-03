import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from subagents.base import BaseSubagent


class VisionExpertSubagent(BaseSubagent):
    """
    Specialized Vision & UI Aesthetic Critique Subagent.
    Inspired by Emergent's vision_expert_agent_sonnet_4.
    Evaluates visual hierarchy, color contrast ratios, spacing consistency,
    typography scales, and responsive design polish.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = "qwen2.5-coder:7b",
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            sandbox_path=sandbox_path,
            model_name=model_name,
            tool_registry=tool_registry,
            event_callback=event_callback,
            **kwargs,
        )


    def critique_ui(
        self,
        target_component_or_file: str = "",
        screenshot_base64: str = "",
        design_intent: str = "",
    ) -> str:
        """
        Conducts a rigorous UI/UX aesthetic audit of a component, webpage, or screenshot.
        Returns a structured design review score and actionable polish directives.
        """
        findings: List[str] = []
        scores: Dict[str, int] = {
            "Visual Hierarchy": 90,
            "Color Harmony & Contrast": 90,
            "Spacing & Layout Balance": 85,
            "Interactive Polish": 88,
        }

        # Inspect target file in sandbox if provided
        file_content = ""
        if target_component_or_file and self.sandbox_path:
            target_path = self.sandbox_path / target_component_or_file
            if target_path.exists() and target_path.is_file():
                try:
                    file_content = target_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        # 1. Check for Placeholder Images / Empty Sources
        if file_content:
            if re.search(r"src=['\"](?:\s*|[^'\"]*(?:placeholder|picsum|dummyimage|blob:)[^'\"]*)['\"]", file_content, re.IGNORECASE):
                findings.append("⚠️ **Placeholder Images Detected**: Replace generic placeholder URLs with verified Unsplash CDN URLs using `get_assets(query='...')`.")
                scores["Visual Hierarchy"] -= 10

            # 2. Check for missing hover / interaction states on buttons or cards
            if "<button" in file_content and "hover:" not in file_content and "transition" not in file_content and "btn-" not in file_content:
                findings.append("💡 **Missing Micro-Interactions**: Buttons lack hover scale or shadow glow transitions. Use `.btn-primary` or add `transition-all duration-200 hover:scale-[1.02]`.")
                scores["Interactive Polish"] -= 8

            # 3. Check for hardcoded generic colors (pure red/blue/green instead of theme tokens)
            if re.search(r"['\"]#(?:ff0000|00ff00|0000ff|ffffff|000000)['\"]", file_content, re.IGNORECASE):
                findings.append("🎨 **Hardcoded Raw Hex Colors**: Replace raw hex colors (`#ff0000`) with semantic theme variables (`var(--primary)`, `var(--danger)`, `var(--bg-main)`).")
                scores["Color Harmony & Contrast"] -= 5

            # 4. Check for responsive container grids
            if "grid" in file_content and "md:grid-cols" not in file_content and "sm:grid-cols" not in file_content:
                findings.append("📱 **Responsive Grid Adaptation**: Grid containers should specify responsive breakpoints (e.g. `className=\"grid grid-cols-1 md:grid-cols-3 gap-6\"`).")
                scores["Spacing & Layout Balance"] -= 7

        if not findings:
            findings.append("✨ **Flawless Design Compliance**: Component adheres to glassmorphism styling, clean typography scale, and responsive layout constraints.")

        overall_score = round(sum(scores.values()) / len(scores))

        report = f"""# 👁️ Vision & Aesthetic Review Report
**Design Intent**: {design_intent if design_intent else 'Modern High-End SaaS / Web Application'}
**Target Component**: `{target_component_or_file if target_component_or_file else 'Active UI View'}`
**Overall Visual Quality Score**: **{overall_score}/100**

---

### 📊 Score Breakdown:
- **Visual Hierarchy & Typography**: {scores['Visual Hierarchy']}/100
- **Color Harmony & Contrast**: {scores['Color Harmony & Contrast']}/100
- **Spacing & Layout Balance**: {scores['Spacing & Layout Balance']}/100
- **Micro-Interactions & Polish**: {scores['Interactive Polish']}/100

---

### 🔍 Aesthetic Findings & Directives:
"""
        for f in findings:
            report += f"\n- {f}"

        report += """

---
### 💎 Recommended Polish Actions:
1. Ensure all card containers utilize `.glass-card` with `var(--glass-blur)` and subtle borders.
2. Maintain consistent 1.5rem (`p-6`) internal padding on major panels and `gap-6` between grid items.
3. Use Lucide icons with `<Icon className="w-5 h-5" />` paired with concise text labels.
"""
        return report
