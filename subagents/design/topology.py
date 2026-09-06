"""
Feature-Driven Component Topology Generator.
Analyzes problem statements to prescribe architectural component hierarchies
mapped directly to the user's actual interaction model (avoiding cookie-cutter dashboard layouts).
"""

from typing import Dict, Any, List


def detect_archetype(problem_statement: str, app_type: str = "") -> Dict[str, Any]:
    """
    Identifies application interaction archetype from the problem statement and app type.
    """
    text = f"{app_type} {problem_statement}".lower()

    if any(k in text for k in ["chat", "message", "conversation", "slack", "discord", "dm", "inbox"]):
        return {
            "name": "Messaging & Real-time Collaboration",
            "components": [
                {
                    "name": "SidebarChannels.jsx",
                    "role": "Channel & DM Navigation",
                    "details": "Filterable list of conversations, presence indicators, and unread badges.",
                },
                {
                    "name": "ChatStream.jsx",
                    "role": "Message Thread Canvas",
                    "details": "Scrollable message history with user avatars, formatted bubbles, timestamps, and reactions.",
                },
                {
                    "name": "MessageInput.jsx",
                    "role": "Composer Dock",
                    "details": "Auto-expanding input with attachment picker, formatting buttons, and keyboard send shortcut.",
                },
                {
                    "name": "ParticipantFlyout.jsx",
                    "role": "Context & User Drawer",
                    "details": "Slide-out panel showing member roles, shared media attachments, and room settings.",
                },
            ],
        }

    elif any(k in text for k in ["draw", "canvas", "design tool", "editor", "paint", "diagram", "audio", "music", "synth", "mixer"]):
        return {
            "name": "Creative Studio & Interactive Canvas",
            "components": [
                {
                    "name": "ToolFloatingDock.jsx",
                    "role": "Primary Tool Switcher",
                    "details": "Floating toolbar with tool selection, brush/knob presets, and undo/redo history.",
                },
                {
                    "name": "InteractiveWorkspace.jsx",
                    "role": "Creative Canvas Core",
                    "details": "Zoomable, pannable interactive canvas supporting pointer events and live feedback.",
                },
                {
                    "name": "PropertyInspector.jsx",
                    "role": "Parameters & Style Palette",
                    "details": "Sidebar controlling dimensions, color fills, effect sliders, and layer typography.",
                },
                {
                    "name": "LayerTimeline.jsx",
                    "role": "Structure & Sequence",
                    "details": "Stack of active visual or audio layers with visibility toggles and solo/mute states.",
                },
            ],
        }

    elif any(k in text for k in ["shop", "store", "commerce", "product", "cart", "checkout", "marketplace"]):
        return {
            "name": "E-Commerce & Digital Storefront",
            "components": [
                {
                    "name": "HeroShowcase.jsx",
                    "role": "Editorial Spotlight",
                    "details": "High-impact visual banner with promotional copy and quick-filter chips.",
                },
                {
                    "name": "CategoryFilterBar.jsx",
                    "role": "Faceted Search & Sorting",
                    "details": "Category pills, price range sliders, and active filter tags.",
                },
                {
                    "name": "ProductCardGrid.jsx",
                    "role": "Catalog Display",
                    "details": "Responsive grid of product cards with image hover zoom, price badges, and quick-add.",
                },
                {
                    "name": "SlideOverCart.jsx",
                    "role": "Checkout Drawer",
                    "details": "Slide-out bag with item quantity steppers, subtotal breakdown, and checkout CTA.",
                },
            ],
        }

    elif any(k in text for k in ["wizard", "onboarding", "form", "step", "survey", "quiz", "stepper"]):
        return {
            "name": "Guided Multi-Step Workflow",
            "components": [
                {
                    "name": "StepProgressBar.jsx",
                    "role": "Progress & Phase Tracker",
                    "details": "Horizontal stepper showing completed, active, and upcoming workflow phases.",
                },
                {
                    "name": "StepFormCanvas.jsx",
                    "role": "Interactive Input Container",
                    "details": "Focal form card with validation states, animated step transitions, and helper text.",
                },
                {
                    "name": "NavigationControls.jsx",
                    "role": "Step Controls & Save",
                    "details": "Back, Save Draft, and Continue buttons with disabled validation triggers.",
                },
                {
                    "name": "LiveSummaryCard.jsx",
                    "role": "Review & Preview Panel",
                    "details": "Live summary preview updating in real-time as the user inputs data.",
                },
            ],
        }

    else:
        return {
            "name": "Productivity & Application Workspace",
            "components": [
                {
                    "name": "WorkspaceNavbar.jsx",
                    "role": "Global Header & Actions",
                    "details": "Brand logo, quick global search bar, view toggles, and primary action CTA.",
                },
                {
                    "name": "KeyMetricsOverview.jsx",
                    "role": "High-Level Health Indicators",
                    "details": "Compact metric cards displaying primary operational numbers, sparklines, and trends.",
                },
                {
                    "name": "InteractiveMainView.jsx",
                    "role": "Data Core & Collection",
                    "details": "Filterable, searchable item grid or table with pagination and status badges.",
                },
                {
                    "name": "DetailInspectorModal.jsx",
                    "role": "Focused Item Drawer / Modal",
                    "details": "Contextual view showing complete item details, action log, and edit capabilities.",
                },
            ],
        }


def format_topology_blueprint(
    archetype: Dict[str, Any],
    theme: Dict[str, Any],
    problem_statement: str,
    app_type: str,
    is_tailwind: bool,
) -> str:
    """Formats the tailored component hierarchy into the markdown blueprint."""
    components: List[Dict[str, str]] = archetype.get("components", [])

    lines = [
        "# 🎨 Bespoke UI/UX Design System Blueprint",
        f"**Aesthetic Identity**: {theme['name']}",
        f"**Application Domain**: {app_type.replace('_', ' ').title() if app_type else 'Modern Web Experience'}",
        f"**Interaction Archetype**: {archetype['name']}",
        f"**Styling Framework**: {'Tailwind CSS (Directives Preserved)' if is_tailwind else 'Bespoke Vanilla CSS'}",
        f"**Typography**: `{theme['font_heading']}` (Display) paired with `Inter` (Body Sans)",
        f"**Color Tokens**: Primary `{theme['primary']}`, Accent `{theme['accent']}`, Canvas `{theme['bg_main']}`",
        "\n---",
        "\n## 🏛️ Tailored Component Architecture:",
    ]

    for idx, comp in enumerate(components, 1):
        lines.append(f"### {idx}. `{comp['name']}` — {comp['role']}")
        lines.append(f"- {comp['details']}")

    lines.extend([
        "\n---",
        "### 💡 Instructions for Main Engineer:",
        "✅ Design system tokens and baseline styles have been written to `src/index.css`.",
        "👉 NOW PROCEED TO IMPLEMENT CODE: Write the Express backend in `server/index.js` and React UI in `src/App.jsx` using `write_file` or `write_files`. Do NOT call `finish` until full application code is written!",
    ])

    return "\n".join(lines)
