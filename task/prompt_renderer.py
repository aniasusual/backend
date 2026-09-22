"""
Jinja2 template renderer for subagent system prompts, user prompts, and yield reminders.
Replicates Oh My Pi prompt assembly logic.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import jinja2

SYSTEM_PROMPTS_DIR = Path(__file__).parent / "prompts" / "system"

# Embedded fallback templates in case prompts directory is inaccessible
FALLBACK_TEMPLATES = {
    "subagent_system_prompt.md": """§ Role
{{ agent.system_prompt }}

{% if context %}
§ Context
{{ context }}
{% endif %}

{% if plan_reference %}
§ Plan
This session is executing an approved plan. Your assignment is one part of it.
Use the plan to understand how your piece fits the whole and to stay consistent with decisions already made. Where the plan and your assignment conflict, the assignment wins. The plan's full contents are below — NEVER re-read it from disk.
<plan path="{{ plan_reference_path }}">
{{ plan_reference }}
</plan>
{% endif %}

§ Coop
You are operating on a piece of work assigned to you by the main agent.

{% if not worktree %}
# Validation
Project-wide validation is the main agent's job, run once after all subagents land. NEVER run formatters, linters, or project-wide builds/test suites unless your assignment explicitly instructs it — siblings edit concurrently; mid-flight validation blocks on their half-finished changes and reports phantom failures. Scoped proof of your own change (single test file, targeted repro, smoke run) is fine.
{% endif %}

{% if worktree %}
# Working Tree
You are working in an isolated Git working tree at `{{ worktree }}` for this sub-task.
You NEVER modify files outside this tree or in the original repository.
{% endif %}

{% if peers %}
# Peers
You can reach other live agents via the `hub` tool. Your ID is `{{ self_id }}`. Currently visible peers:
{% for peer in peers %}
- `{{ peer.id }}` — {{ peer.agent }} ({{ peer.status }})
{% endfor %}

Use `hub` messaging only for quick coordination, never long-form content. Address peers by id or use "all" to broadcast.
- Discovery: `hub` op:"list" refreshes the live view.
- Coordination: Before you edit a file or start work a sibling may already own, message that peer first (`hub` op:"send", to="<peer-id>").
- Follow-up: Answer peer questions promptly (set `replyTo`).
{% endif %}

§ Completion
No progress updates, narrative, or TODO lists. Execute; report results with `yield`.

While work remains, you MUST continue with another tool call — investigate, edit, run, verify. Save findings for your `yield` call.

{% if output_schema %}
Your terminal `yield` MUST strictly use this shape — the schema fields go inside `data`:
```json
{{ output_schema | tojson(indent=2) }}
```
{% else %}
Call `yield` with your findings and deliverables in `data`.
{% endif %}

Giving up is a last resort. If truly blocked, you MUST call `yield` with `{ error: "exact blocker description" }`.
You NEVER give up due to uncertainty or missing info obtainable via tools.
You MUST keep going until this assignment is concluded.
""",
    "subagent_user_prompt.md": """Complete assignment thoroughly:

{{ assignment }}
""",
    "yield_reminder.md": """{% if budget_stop %}
Soft request budget reached. You MUST now conclude your work and call `yield` with your final findings or summary immediately.
{% else %}
Reminder ({{ retry_count }}/{{ max_retries }}): You have completed tool actions but did not call `yield`. 
You MUST call the `yield` tool now to deliver your report and conclude this assignment.
{% endif %}
""",
}

# Shared Jinja2 environment configured for markdown files with fallback
_jinja_env = jinja2.Environment(
    loader=jinja2.ChoiceLoader([
        jinja2.FileSystemLoader(str(SYSTEM_PROMPTS_DIR)),
        jinja2.DictLoader(FALLBACK_TEMPLATES),
    ]),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

def render_subagent_system_prompt(
    agent_definition: Any,
    context: Optional[str] = None,
    plan_reference: Optional[str] = None,
    plan_reference_path: Optional[str] = None,
    worktree: Optional[str] = None,
    self_id: Optional[str] = None,
    peers: Optional[List[Dict[str, Any]]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Render the system prompt for a subagent incorporating its role, batch context,
    plan references, isolation tree, active peer roster, and yield output schema.
    """
    template = _jinja_env.get_template("subagent_system_prompt.md")
    return template.render(
        agent=agent_definition,
        context=context.strip() if context else "",
        plan_reference=plan_reference.strip() if plan_reference else "",
        plan_reference_path=plan_reference_path or "",
        worktree=worktree or "",
        self_id=self_id or "",
        peers=peers or [],
        output_schema=output_schema,
    )


def render_subagent_user_prompt(assignment: str) -> str:
    """
    Render the initial user prompt for a subagent assignment.
    """
    template = _jinja_env.get_template("subagent_user_prompt.md")
    return template.render(assignment=assignment.strip())


def render_yield_reminder(
    retry_count: int = 1,
    max_retries: int = 3,
    budget_stop: bool = False,
) -> str:
    """
    Render the yield reminder prompt when an agent finishes an action turn without calling yield.
    """
    template = _jinja_env.get_template("yield_reminder.md")
    return template.render(
        retry_count=retry_count,
        max_retries=max_retries,
        budget_stop=budget_stop,
    )
