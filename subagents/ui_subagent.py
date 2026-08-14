import json
import time
from playwright.sync_api import sync_playwright
import ollama

from config.prompts import UI_SUBAGENT_PROMPT

class UITestingSubagent:
    """
    A specialized subagent that uses Playwright and an LLM to interactively test a web UI.
    """
    def __init__(self, model_name: str = "qwen2.5-coder:7b", max_steps: int = 15):
        self.model_name = model_name
        self.max_steps = max_steps

    def _extract_interactive_elements(self, page):
        """Enhanced DOM extraction script that captures buttons, links, inputs, and anything clickable or focusable."""
        js_script = """
        () => {
            let elements = [];
            let index = 0;
            // Select all potentially interactive elements
            const interactives = document.querySelectorAll('button, a, input, textarea, select, [role="button"], [role="link"], [role="checkbox"], [role="menuitem"], [role="tab"], [onclick], [tabindex]');
            
            interactives.forEach(el => {
                // Skip hidden elements or those with negative tabindex
                if (el.offsetParent === null) return;
                if (el.getAttribute('tabindex') && parseInt(el.getAttribute('tabindex')) < 0) return;
                
                let id = 'el_' + index++;
                el.setAttribute('data-test-id', id);
                
                let tag = el.tagName.toLowerCase();
                let text = el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '';
                text = text.substring(0, 100).replace(/\\n/g, ' ').trim();
                
                let role = el.getAttribute('role') || '';
                
                elements.push({
                    id: id,
                    tag: tag,
                    text: text,
                    type: el.type || role
                });
            });
            return elements;
        }
        """
        return page.evaluate(js_script)

    def run_ui_test(self, url: str, instructions: str) -> str:
        messages = [
            {"role": "system", "content": UI_SUBAGENT_PROMPT},
            {"role": "user", "content": f"Instructions: {instructions}\n\nNavigate to {url} and begin testing. Check the functionality."}
        ]
        
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Navigate and handle potential connection issues
                try:
                    page.goto(url, wait_until="networkidle", timeout=10000)
                except Exception as e:
                    return f"Subagent Error: Could not load URL {url}. Make sure the server is actually running. Details: {str(e)}"
                
                state_desc = "Unknown"
                
                for step in range(self.max_steps):
                    time.sleep(1) # Wait for React/UI state to settle
                    
                    # Extract state
                    elements = self._extract_interactive_elements(page)
                    state_desc = "Current interactive elements:\n"
                    for el in elements:
                        state_desc += f"- [{el['id']}] <{el['tag']} type='{el['type']}'> {el['text']}\n"
                    
                    if not elements:
                        state_desc += "No interactive elements found on the page (or page is blank).\n"
                    
                    messages.append({"role": "user", "content": state_desc})
                    
                    # Query LLM
                    response = ollama.chat(model=self.model_name, messages=messages)
                    assistant_msg = response['message']['content'].strip()
                    messages.append({"role": "assistant", "content": assistant_msg})
                    
                    # Parse JSON
                    try:
                        # Strip markdown if LLM disobeys
                        if assistant_msg.startswith("```json"):
                            assistant_msg = assistant_msg[7:-3].strip()
                        elif assistant_msg.startswith("```"):
                            assistant_msg = assistant_msg[3:-3].strip()
                            
                        action = json.loads(assistant_msg)
                    except Exception as e:
                        messages.append({"role": "user", "content": f"Invalid JSON response. Remember to reply ONLY with a JSON object. No extra text."})
                        continue
                        
                    act = action.get("action")
                    if act == "done":
                        browser.close()
                        return action.get("report", "Testing completed, no report provided.")
                    elif act == "click":
                        el_id = action.get("id")
                        try:
                            page.click(f"[data-test-id='{el_id}']", timeout=2000)
                            messages.append({"role": "user", "content": f"Clicked element {el_id}."})
                        except Exception as e:
                            messages.append({"role": "user", "content": f"Error clicking element {el_id}: {str(e)}"})
                    elif act == "type":
                        el_id = action.get("id")
                        text = action.get("text", "")
                        try:
                            page.fill(f"[data-test-id='{el_id}']", text, timeout=2000)
                            messages.append({"role": "user", "content": f"Typed '{text}' into element {el_id}."})
                        except Exception as e:
                            messages.append({"role": "user", "content": f"Error typing in element {el_id}: {str(e)}"})
                    else:
                        messages.append({"role": "user", "content": f"Unknown action: {act}. Valid actions are 'click', 'type', 'done'."})
                
                browser.close()
                return f"UI testing subagent stopped after {self.max_steps} steps without calling 'done'. Last state: {state_desc}"
            except Exception as e:
                return f"Failed to run UI testing subagent: {str(e)}"
