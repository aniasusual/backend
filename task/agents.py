"""
Agent definition parser and bundled agent loader.
Replicates Oh My Pi's task/agents.ts.
"""

import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import yaml

from .types import AgentDefinition, AgentSource

logger = logging.getLogger(__name__)

# Directory containing bundled agent definitions
BUNDLED_AGENTS_DIR = Path(__file__).parent / "prompts" / "agents"

# Thread-safe in-memory cache for bundled agents
_cache_lock = threading.Lock()
_bundled_agents_cache: Optional[Dict[str, AgentDefinition]] = None


def extract_frontmatter_and_body(text: str) -> Tuple[Optional[str], str]:
    """
    Extract YAML frontmatter and body from markdown text.
    Handles UTF-8 BOM, Windows line endings, trailing whitespace on delimiter lines,
    and occurrences of '---' inside YAML values.
    Returns (frontmatter_raw, body) or (None, full_text) if no frontmatter.
    """
    if not text:
        return None, ""

    # Strip UTF-8 BOM if present
    if text.startswith("\ufeff"):
        text = text[1:]

    lines = text.splitlines(keepends=True)
    if not lines:
        return None, ""

    # Find the opening delimiter: must be first line (ignoring any leading blank lines)
    start_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "---":
            start_idx = i
            break
        return None, text

    if start_idx == -1:
        return None, text

    # Find the closing delimiter: must be on its own line
    end_idx = -1
    for i in range(start_idx + 1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        return None, text

    frontmatter_raw = "".join(lines[start_idx + 1 : end_idx])
    body = "".join(lines[end_idx + 1 :])
    return frontmatter_raw, body


def parse_agent_markdown(
    file_path: Optional[Union[str, Path]] = None,
    content: Optional[str] = None,
    source: AgentSource = "bundled",
) -> AgentDefinition:
    """
    Parse an agent definition from markdown content with YAML frontmatter.
    If frontmatter is missing or invalid, treats the body as system prompt.
    """
    path_obj = Path(file_path) if file_path else None
    text = content if content is not None else (path_obj.read_text(encoding="utf-8", errors="replace") if path_obj else "")

    frontmatter_raw, body = extract_frontmatter_and_body(text)
    if frontmatter_raw is None:
        name = path_obj.stem if path_obj else "custom_agent"
        return AgentDefinition(
            name=name,
            description="Custom subagent worker",
            system_prompt=text.strip(),
            source=source,
            file_path=str(path_obj) if path_obj else None,
        )

    try:
        loaded = yaml.safe_load(frontmatter_raw)
        meta = loaded if isinstance(loaded, dict) else {}
        if loaded is not None and not isinstance(loaded, dict):
            logger.warning(
                "Frontmatter in %s is not a dictionary (got %s); ignoring metadata",
                path_obj or "<content>",
                type(loaded).__name__,
            )
    except yaml.YAMLError as err:
        logger.warning(
            "YAML parse error in %s: %s; falling back to default agent config",
            path_obj or "<content>",
            err,
        )
        meta = {}

    # 1. Tools: support comma-separated string or list; deduplicate preserving order
    tools_val = meta.get("tools")
    if isinstance(tools_val, str):
        raw_tools = [t.strip() for t in tools_val.split(",") if t.strip()]
    elif isinstance(tools_val, list):
        raw_tools = [str(t).strip() for t in tools_val if str(t).strip()]
    else:
        raw_tools = []
    seen = set()
    tools = [t for t in raw_tools if not (t in seen or seen.add(t))]

    # 2. Name: strip whitespace, fallback to filename stem or 'agent'
    name_raw = meta.get("name")
    if name_raw is not None and str(name_raw).strip():
        name = str(name_raw).strip()
    elif path_obj:
        name = path_obj.stem
    else:
        name = "agent"

    # 3. Description
    description = str(meta.get("description") or "").strip()

    # 4. Model
    model_val = meta.get("model")
    model = str(model_val).strip() if model_val is not None and str(model_val).strip() else None

    # 5. Thinking Level: check aliases
    thinking_val = None
    for k in ("thinking-level", "thinkingLevel", "thinking_level"):
        if k in meta and meta[k] is not None:
            thinking_val = meta[k]
            break
    thinking_level = str(thinking_val).strip() if thinking_val is not None and str(thinking_val).strip() else None

    # 6. Spawns: handle string ('*', 'scout, reviewer'), YAML list (['scout', 'reviewer']), booleans, or None
    spawns_val = meta.get("spawns")
    if spawns_val is None:
        spawns = None
    elif isinstance(spawns_val, list):
        spawns_items = [str(s).strip() for s in spawns_val if str(s).strip()]
        spawns = ", ".join(spawns_items) if spawns_items else None
    elif isinstance(spawns_val, str):
        spawns_str = spawns_val.strip()
        if spawns_str.lower() in ("none", "false", "null", ""):
            spawns = None
        else:
            spawns = spawns_str
    elif isinstance(spawns_val, bool):
        spawns = "*" if spawns_val else None
    else:
        spawns = str(spawns_val).strip()

    # 7. Blocking: safe boolean parsing
    blocking_val = meta.get("blocking", False)
    if isinstance(blocking_val, str):
        blocking = blocking_val.strip().lower() in ("true", "1", "yes")
    else:
        blocking = bool(blocking_val)

    # 8. Output Schema: check aliases
    output_schema = None
    for k in ("output", "output_schema", "outputSchema"):
        if k in meta and isinstance(meta[k], dict):
            output_schema = meta[k]
            break

    # 9. Read-Summarize: check aliases and safe boolean parsing
    read_summarize_val = None
    for k in ("read-summarize", "read_summarize", "readSummarize"):
        if k in meta and meta[k] is not None:
            read_summarize_val = meta[k]
            break
    if read_summarize_val is None:
        read_summarize = True
    elif isinstance(read_summarize_val, str):
        read_summarize = read_summarize_val.strip().lower() not in ("false", "0", "no")
    else:
        read_summarize = bool(read_summarize_val)

    # 10. Normalize source
    valid_sources = ("bundled", "user", "project")
    norm_source: AgentSource = source if source in valid_sources else "bundled"

    return AgentDefinition(
        name=name,
        description=description,
        tools=tools,
        model=model,
        thinking_level=thinking_level,
        spawns=spawns,
        blocking=blocking,
        output_schema=output_schema,
        read_summarize=read_summarize,
        system_prompt=body.strip(),
        source=norm_source,
        file_path=str(path_obj) if path_obj else None,
    )


def load_bundled_agents(prompts_dir: Optional[Path] = None) -> Dict[str, AgentDefinition]:
    """
    Load and cache all bundled agent definitions from backend/task/prompts/agents/*.md.
    Returns a shallow copy to prevent callers from mutating the internal cache.
    """
    global _bundled_agents_cache
    if prompts_dir is None:
        with _cache_lock:
            if _bundled_agents_cache is not None:
                return dict(_bundled_agents_cache)

    target_dir = prompts_dir or BUNDLED_AGENTS_DIR
    agents: Dict[str, AgentDefinition] = {}

    if target_dir.exists() and target_dir.is_dir():
        for md_file in sorted(target_dir.glob("*.md")):
            try:
                defn = parse_agent_markdown(md_file, source="bundled")
                agents[defn.name] = defn
            except Exception as err:
                logger.warning("Failed to parse bundled agent %s: %s", md_file.name, err)

    if prompts_dir is None:
        with _cache_lock:
            _bundled_agents_cache = agents
        return dict(agents)
    return agents


def get_bundled_agent(name: str) -> Optional[AgentDefinition]:
    """Retrieve a bundled agent by name."""
    return load_bundled_agents().get(name)


def clear_bundled_agents_cache() -> None:
    """Clear the cached bundled agents (thread-safe, useful for testing)."""
    global _bundled_agents_cache
    with _cache_lock:
        _bundled_agents_cache = None
