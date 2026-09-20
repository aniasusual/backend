"""
Goal-Driven Autonomous UI & Browser Testing Prompts and Tool Schemas.
Provides formal Ollama tool-calling definitions and system prompts for live SDET verification.
"""

from typing import List, Dict, Any

BROWSER_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an interactive element on the webpage by its observation ID (e.g. 'el_0').",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Target element ID from the latest DOM observation (e.g. 'el_0').",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of what flow or action this click executes.",
                    },
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type text into an input field or textarea identified by its observation ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Target input or textarea element ID (e.g. 'el_1').",
                    },
                    "text": {
                        "type": "string",
                        "description": "The exact text or value to type into the field.",
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "Whether to press Enter after typing to submit the field/form (default: false).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of what data is being inputted.",
                    },
                },
                "required": ["id", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_select",
            "description": "Select an option from a dropdown or select element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Target select element ID (e.g. 'el_2').",
                    },
                    "value": {
                        "type": "string",
                        "description": "The option value or visible text to select.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of why this option is selected.",
                    },
                },
                "required": ["id", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_hover",
            "description": "Hover mouse over an element to trigger CSS hover effects, tooltips, or dropdown menus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Target element ID to hover over (e.g. 'el_3').",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for hovering (e.g. 'reveal hover menu or tooltip').",
                    },
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press_key",
            "description": "Press a keyboard key (e.g. 'Escape' to dismiss modals, 'Tab' to change focus, 'Enter', 'ArrowDown').",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key name to press (e.g. 'Escape', 'Enter', 'Tab', 'ArrowDown'). Default is 'Escape'.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for pressing the key (e.g. 'close open modal').",
                    },
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_drag_and_drop",
            "description": "Drag an element onto another element (for Kanban boards, sortable lists, sliders).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_id": {
                        "type": "string",
                        "description": "Observation ID of the element to drag (e.g. 'el_1').",
                    },
                    "target_id": {
                        "type": "string",
                        "description": "Observation ID of the drop target container/element (e.g. 'el_5').",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for dragging (e.g. 'move card from Todo to In Progress column').",
                    },
                },
                "required": ["source_id", "target_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_upload_file",
            "description": "Select and upload a local file into a file input element (<input type='file'>) without opening an OS dialog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Observation ID of the file input element (e.g. 'el_4').",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to upload.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for uploading this file.",
                    },
                },
                "required": ["id", "file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the active viewport up or down to reveal below-the-fold controls or content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["down", "up"],
                        "description": "Scroll direction: 'down' (default) or 'up'.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for scrolling (e.g. 'reveal submit button at bottom of page').",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait",
            "description": "Pause briefly (0.5 to 3.0 seconds) to allow animations, transitions, or asynchronous API calls to settle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "description": "Seconds to pause (default: 1.0, max: 3.0).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Explanation of what event or transition is being waited on.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_assert_text",
            "description": "Assert that specific text is currently visible on the page (verifies successful creation, toast alert, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Exact text expected to be visible on the live webpage.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this text assertion verifies the workflow.",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate the browser to a specific sub-route or URL within the application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The destination URL or path to navigate to.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for navigating to this URL.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_finish",
            "description": "Conclude the testing session and return the final audit verdict to the main engineer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["PASSED", "FAILED"],
                        "description": "'PASSED' if all requested flows function without regressions; 'FAILED' if blocking bugs, crashes, or 500s occur.",
                    },
                    "report": {
                        "type": "string",
                        "description": "Factual summary of tested workflows, observed outcomes, and verification evidence.",
                    },
                    "fix_instructions": {
                        "type": "string",
                        "description": "Precise, actionable instructions for the engineer to fix any detected defect, or 'None' if all tests passed.",
                    },
                },
                "required": ["status", "report"],
            },
        },
    },
]

SDET_SYSTEM_PROMPT = """You are a Senior Staff SDET & Browser Automation Specialist conducting autonomous, live end-to-end verification of a web application.
Your mission is to interactively drive the browser, execute user workflows according to the assigned instructions, verify that state changes occur in the DOM, and report any crashes or regressions.

### CRITICAL EXECUTION RULES:
1. **TOOL INVOCATION MANDATE (ZERO UNPARSEABLE TURNS)**:
   - On EVERY single turn, you MUST call exactly one browser tool.
   - Never output conversational chatter or unstructured thoughts without invoking a tool call.
   - If user flows are verified or if a blocking defect/crash occurs, immediately invoke `browser_finish`.

2. **DYNAMIC OBSERVATION & ELEMENT IDs**:
   - The webpage state updates dynamically after every action. Elements are assigned temporary IDs (`el_0`, `el_1`, ...) on each step.
   - ALWAYS refer to element IDs from the **latest observation**. Never guess IDs or use IDs from earlier steps.

3. **REACT & INTERACTIVE WORKFLOWS**:
   - **Form Inputs**: Enter realistic test data using `browser_type(id=..., text=...)`. If submitting via Enter, set `press_enter=True`. If there is a dedicated Submit/Add button, click it with `browser_click`.
   - **Verify Outcomes Before Concluding**: Never call `browser_finish(status='PASSED')` immediately after an action without verifying the result in the DOM. Always verify that the expected item, message, or state update is visible (use `browser_assert_text` or verify it appears in the updated interactive controls list).
   - **Async State Settling**: If an action triggers an asynchronous backend API call or animated transition, call `browser_wait(seconds=1.0)` to allow the state to settle before asserting.

4. **FAULT DETECTION & AUDITING**:
   - Actively inspect in-DOM error alerts, browser console logs, and network failures presented in each observation.
   - If an action crashes the app, an assertion fails, or an endpoint returns 500, conclude immediately with `browser_finish(status='FAILED', report='...', fix_instructions='...')` detailing exact reproduction steps and the root cause for the main engineer.
"""

