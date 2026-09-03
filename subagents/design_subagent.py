from pathlib import Path
from typing import Dict, Any, Optional

from subagents.base import BaseSubagent


# Curated, aesthetically stunning design palettes inspired by award-winning web design
# Each theme provides cohesive HSL variables, shadows, glassmorphism tokens, and Google Fonts.
THEME_PALETTES: Dict[str, Dict[str, Any]] = {
    "dark_glass_indigo": {
        "name": "Dark Glassmorphism Indigo",
        "font_heading": "Outfit, sans-serif",
        "font_body": "Inter, sans-serif",
        "google_fonts_url": "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700;800&display=swap",
        "colors": {
            "--bg-main": "#090d16",
            "--bg-surface": "rgba(17, 24, 39, 0.75)",
            "--bg-card": "rgba(30, 41, 59, 0.55)",
            "--bg-card-hover": "rgba(51, 65, 85, 0.65)",
            "--border-subtle": "rgba(255, 255, 255, 0.08)",
            "--border-glow": "rgba(99, 102, 241, 0.35)",
            "--primary": "#6366f1",
            "--primary-hover": "#4f46e5",
            "--primary-glow": "rgba(99, 102, 241, 0.25)",
            "--accent": "#06b6d4",
            "--accent-glow": "rgba(6, 182, 212, 0.25)",
            "--success": "#10b981",
            "--warning": "#f59e0b",
            "--danger": "#ef4444",
            "--text-primary": "#f8fafc",
            "--text-secondary": "#94a3b8",
            "--text-muted": "#64748b",
            "--glass-blur": "16px",
            "--radius-sm": "8px",
            "--radius-md": "12px",
            "--radius-lg": "20px",
            "--shadow-card": "0 8px 32px 0 rgba(0, 0, 0, 0.37)",
            "--shadow-glow": "0 0 25px rgba(99, 102, 241, 0.3)",
        },
    },
    "emerald_fintech": {
        "name": "Emerald Wealth & Fintech",
        "font_heading": "Plus Jakarta Sans, sans-serif",
        "font_body": "Inter, sans-serif",
        "google_fonts_url": "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap",
        "colors": {
            "--bg-main": "#06130d",
            "--bg-surface": "rgba(10, 31, 22, 0.75)",
            "--bg-card": "rgba(16, 48, 35, 0.5)",
            "--bg-card-hover": "rgba(24, 71, 52, 0.6)",
            "--border-subtle": "rgba(16, 185, 129, 0.15)",
            "--border-glow": "rgba(16, 185, 129, 0.4)",
            "--primary": "#10b981",
            "--primary-hover": "#059669",
            "--primary-glow": "rgba(16, 185, 129, 0.3)",
            "--accent": "#34d399",
            "--accent-glow": "rgba(52, 211, 153, 0.25)",
            "--success": "#10b981",
            "--warning": "#f59e0b",
            "--danger": "#f43f5e",
            "--text-primary": "#f0fdf4",
            "--text-secondary": "#a7f3d0",
            "--text-muted": "#6ee7b7",
            "--glass-blur": "14px",
            "--radius-sm": "8px",
            "--radius-md": "14px",
            "--radius-lg": "24px",
            "--shadow-card": "0 12px 35px -5px rgba(6, 78, 59, 0.3)",
            "--shadow-glow": "0 0 25px rgba(16, 185, 129, 0.35)",
        },
    },
    "violet_cyberpunk": {
        "name": "Violet Neon Cyberpunk",
        "font_heading": "Space Grotesk, sans-serif",
        "font_body": "Inter, sans-serif",
        "google_fonts_url": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap",
        "colors": {
            "--bg-main": "#0d0618",
            "--bg-surface": "rgba(24, 11, 43, 0.75)",
            "--bg-card": "rgba(42, 19, 77, 0.55)",
            "--bg-card-hover": "rgba(63, 29, 115, 0.65)",
            "--border-subtle": "rgba(168, 85, 247, 0.2)",
            "--border-glow": "rgba(236, 72, 153, 0.4)",
            "--primary": "#a855f7",
            "--primary-hover": "#9333ea",
            "--primary-glow": "rgba(168, 85, 247, 0.35)",
            "--accent": "#ec4899",
            "--accent-glow": "rgba(236, 72, 153, 0.35)",
            "--success": "#10b981",
            "--warning": "#eab308",
            "--danger": "#ef4444",
            "--text-primary": "#faf5ff",
            "--text-secondary": "#e9d5ff",
            "--text-muted": "#c084fc",
            "--glass-blur": "18px",
            "--radius-sm": "6px",
            "--radius-md": "12px",
            "--radius-lg": "18px",
            "--shadow-card": "0 8px 30px rgba(168, 85, 247, 0.2)",
            "--shadow-glow": "0 0 30px rgba(236, 72, 153, 0.4)",
        },
    },
    "minimal_clean_slate": {
        "name": "Clean Modern Minimalist",
        "font_heading": "Inter, sans-serif",
        "font_body": "Inter, sans-serif",
        "google_fonts_url": "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
        "colors": {
            "--bg-main": "#0f172a",
            "--bg-surface": "rgba(30, 41, 59, 0.8)",
            "--bg-card": "rgba(51, 65, 85, 0.4)",
            "--bg-card-hover": "rgba(71, 85, 105, 0.5)",
            "--border-subtle": "rgba(255, 255, 255, 0.1)",
            "--border-glow": "rgba(56, 189, 248, 0.3)",
            "--primary": "#38bdf8",
            "--primary-hover": "#0284c7",
            "--primary-glow": "rgba(56, 189, 248, 0.2)",
            "--accent": "#f43f5e",
            "--accent-glow": "rgba(244, 63, 94, 0.2)",
            "--success": "#22c55e",
            "--warning": "#f59e0b",
            "--danger": "#ef4444",
            "--text-primary": "#f8fafc",
            "--text-secondary": "#cbd5e1",
            "--text-muted": "#94a3b8",
            "--glass-blur": "12px",
            "--radius-sm": "6px",
            "--radius-md": "10px",
            "--radius-lg": "16px",
            "--shadow-card": "0 4px 20px rgba(0, 0, 0, 0.25)",
            "--shadow-glow": "0 0 20px rgba(56, 189, 248, 0.25)",
        },
    },
}


class DesignSubagent(BaseSubagent):
    """
    Specialized Design Subagent (inspired by Emergent's design_agent_v1).
    Synthesizes problem statements into tailored, production-ready CSS design systems,
    Google Font pairings, dark mode glassmorphism tokens, and responsive UI layout blueprints.
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


    def select_theme_for_domain(self, problem_statement: str, app_type: str = "", theme_preference: str = "") -> Dict[str, Any]:
        """Determines the most visually appropriate theme based on user preferences and application domain."""
        combined_text = f"{problem_statement} {app_type} {theme_preference}".lower()

        if any(w in combined_text for w in ["finance", "crypto", "trading", "wealth", "money", "invest", "stock", "bank", "emerald"]):
            return THEME_PALETTES["emerald_fintech"]
        elif any(w in combined_text for w in ["cyberpunk", "gaming", "neon", "violet", "purple", "party", "music", "night", "futuristic"]):
            return THEME_PALETTES["violet_cyberpunk"]
        elif any(w in combined_text for w in ["minimal", "clean", "slate", "document", "notes", "blog", "portfolio", "simple"]):
            return THEME_PALETTES["minimal_clean_slate"]
        else:
            return THEME_PALETTES["dark_glass_indigo"]

    def generate_index_css(self, theme: Dict[str, Any]) -> str:
        """Generates a complete, production-grade index.css file with CSS variables and utility classes."""
        css_vars = "\n".join(f"  {k}: {v};" for k, v in theme["colors"].items())
        google_font_import = f"@import url('{theme['google_fonts_url']}');"

        return f"""/* ==========================================================================
   LOWKEY DESIGN SYSTEM — {theme['name']}
   Generated by DesignSubagent
   ========================================================================== */

{google_font_import}

:root {{
  font-family: {theme['font_body']};
  color-scheme: dark;
  line-height: 1.5;
  font-weight: 400;

  /* Theme Tokens */
{css_vars}
}}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

body {{
  background-color: var(--bg-main);
  color: var(--text-primary);
  font-family: {theme['font_body']};
  min-height: 100vh;
  overflow-x: hidden;
  background-image: 
    radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.1) 0px, transparent 50%);
  background-attachment: fixed;
}}

h1, h2, h3, h4, h5, h6 {{
  font-family: {theme['font_heading']};
  color: var(--text-primary);
  font-weight: 700;
  letter-spacing: -0.025em;
}}

/* ==========================================================================
   Glassmorphism & Card Utility Classes
   ========================================================================== */

.glass-panel {{
  background: var(--bg-surface);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
}}

.glass-card {{
  background: var(--bg-card);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}}

.glass-card:hover {{
  background: var(--bg-card-hover);
  border-color: var(--border-glow);
  transform: translateY(-2px);
  box-shadow: var(--shadow-glow), var(--shadow-card);
}}

/* ==========================================================================
   Button & Interactive Tokens
   ========================================================================== */

.btn-primary {{
  background: linear-gradient(135deg, var(--primary), var(--primary-hover));
  color: #ffffff;
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-sm);
  font-weight: 600;
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s ease;
  box-shadow: 0 4px 14px var(--primary-glow);
}}

.btn-primary:hover {{
  transform: translateY(-1px);
  box-shadow: 0 6px 20px var(--primary-glow);
}}

.btn-secondary {{
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-sm);
  font-weight: 500;
  border: 1px solid var(--border-subtle);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s ease;
}}

.btn-secondary:hover {{
  background: var(--bg-card-hover);
  border-color: var(--border-glow);
}}

/* ==========================================================================
   Badge & Status Pills
   ========================================================================== */

.badge {{
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  border: 1px solid var(--border-subtle);
  background: var(--bg-card);
}}

.badge-success {{
  color: var(--success);
  border-color: rgba(16, 185, 129, 0.3);
  background: rgba(16, 185, 129, 0.1);
}}

.badge-primary {{
  color: var(--primary);
  border-color: var(--border-glow);
  background: var(--primary-glow);
}}

/* ==========================================================================
   Input & Form Controls
   ========================================================================== */

input, textarea, select {{
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  padding: 0.625rem 0.875rem;
  font-family: inherit;
  font-size: 0.875rem;
  width: 100%;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}}

input:focus, textarea:focus, select:focus {{
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}}

input::placeholder, textarea::placeholder {{
  color: var(--text-muted);
}}
"""

    def generate_layout_blueprint(
        self,
        problem_statement: str,
        app_type: str = "saas_app",
        theme_preference: str = "",
        auto_apply_css: bool = True,
    ) -> str:
        """
        Synthesizes the problem statement into a comprehensive UI/UX design blueprint
        and optionally writes the baseline design system directly into src/index.css.
        """
        theme = self.select_theme_for_domain(problem_statement, app_type, theme_preference)
        index_css_content = self.generate_index_css(theme)

        # If sandbox_path is provided and auto_apply_css is True, apply baseline index.css
        css_applied_msg = ""
        if auto_apply_css and self.sandbox_path:
            css_file = self.sandbox_path / "src" / "index.css"
            try:
                css_file.parent.mkdir(parents=True, exist_ok=True)
                css_file.write_text(index_css_content, encoding="utf-8")
                css_applied_msg = "\n✅ **Design System Applied**: Wrote theme tokens and glassmorphism utilities to `src/index.css`."
            except Exception as e:
                css_applied_msg = f"\n⚠️ Note: Could not auto-write to `src/index.css`: {str(e)}"

        # Generate Component Blueprint Outline
        blueprint_report = f"""# 🎨 UI/UX Design System Blueprint
**Theme Selected**: {theme['name']}
**Typography**: Heading: `{theme['font_heading']}` | Body: `{theme['font_body']}`
**Color Palette**: Primary: `{theme['colors']['--primary']}` | Accent: `{theme['colors']['--accent']}` | Background: `{theme['colors']['--bg-main']}`
{css_applied_msg}

---

## 🏛️ Recommended Application Layout Structure:

### 1. Header / Navigation (`src/components/Navbar.jsx`)
- **Brand Logo & Title**: Modern icon (`<LayoutDashboard />` or domain icon) with gradient text heading.
- **Global Search Bar**: Glassmorphic input field with shortcut badge (`⌘K`).
- **Quick Action Controls**: Primary Action CTA (`btn-primary`), Notification bell pill, User Avatar image.

### 2. Hero & Real-Time Stats Grid (`src/components/StatsGrid.jsx` or Hero View)
- **Top Metrics Row**: 3–4 `.glass-card` metric cards displaying key counts/metrics with Lucide status badges (`badge-success` with `<TrendingUp />`).
- **Interactive Visual**: Main data visual, charts, or interactive canvas with subtle glow shadow (`--shadow-glow`).

### 3. Interactive Main Core (`src/components/MainView.jsx`)
- **Action Toolbar**: Filter pills, category selectors, and search filters.
- **Content Cards / Table**: Responsive CSS Grid (1 col on mobile, 2–3 cols on desktop) displaying items with hover elevation.
- **Empty & Loading States**: Clean empty state with icon and "Create New" CTA when zero records are present.

### 4. Micro-Interactions & Visual Polish Directives:
- **Hover Transitions**: Use `.glass-card` for cards to give a smooth `-2px` float and border glow on hover.
- **Images**: Use `get_assets(query='...')` to fetch verified Unsplash CDN URLs instead of static gray placeholders.
- **Icons**: Import all icons from `lucide-react`.

---
### 💡 Next Mandatory Step for Agent:
✅ Theme tokens and styles have been applied to `src/index.css`.
👉 NOW PROCEED TO IMPLEMENT CODE: Write the Express API routes in `server/index.js` and the React UI components in `src/App.jsx` using `write_file` or `write_files`. Do NOT call `finish` until all application code is fully written!
"""
        return blueprint_report
