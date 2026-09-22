"""
Hierarchical agent discovery from filesystem.
Replicates Oh My Pi's task/discovery.ts.

Discovery precedence (highest wins):
1. Project-level: `<project_root>/.lowkey/agents/*.md`
2. User-level: `~/.lowkey/agents/*.md`
3. Bundled: `backend/task/prompts/agents/*.md`
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from .types import AgentDefinition, AgentSource
from .agents import load_bundled_agents, parse_agent_markdown

logger = logging.getLogger(__name__)


def load_agents_from_dir(directory: Path, source: AgentSource) -> Dict[str, AgentDefinition]:
    """Load and parse all agent definitions from a specific directory."""
    agents: Dict[str, AgentDefinition] = {}
    try:
        if not directory.exists() or not directory.is_dir():
            return agents
    except OSError as err:
        logger.warning("Cannot access agent directory %s: %s", directory, err)
        return agents

    try:
        md_files = sorted(directory.glob("*.md"))
    except OSError as err:
        logger.warning("Failed to list files in %s: %s", directory, err)
        return agents

    for md_file in md_files:
        try:
            agent = parse_agent_markdown(md_file, source=source)
            agents[agent.name] = agent
        except Exception as err:
            logger.warning("Failed to parse agent definition from %s: %s", md_file, err)

    return agents


def discover_agents(
    project_root: Optional[Union[str, Path]] = None,
    home_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, AgentDefinition]:
    """
    Discover all available agents following standard 3-tier precedence:
    Bundled -> User (~/.lowkey/agents) -> Project (<project_root>/.lowkey/agents).
    """
    discovered: Dict[str, AgentDefinition] = {}

    # 1. Bundled agents (base precedence)
    discovered.update(load_bundled_agents())

    # 2. User-level agents: ~/.lowkey/agents/*.md (overrides bundled)
    user_home: Optional[Path] = None
    if home_dir is not None and str(home_dir).strip():
        user_home = Path(home_dir).resolve()
    else:
        try:
            user_home = Path.home()
        except Exception as err:
            logger.debug("Could not resolve user home directory: %s", err)
            user_home = None

    if user_home:
        user_agents_dir = user_home / ".lowkey" / "agents"
        discovered.update(load_agents_from_dir(user_agents_dir, source="user"))

    # 3. Project-level agents: <project_root>/.lowkey/agents/*.md (highest precedence)
    if project_root is not None and str(project_root).strip():
        proj_root_path = Path(project_root).resolve()
        project_agents_dir = proj_root_path / ".lowkey" / "agents"
        discovered.update(load_agents_from_dir(project_agents_dir, source="project"))

    return discovered


def get_agent(
    name: str,
    project_root: Optional[Union[str, Path]] = None,
    home_dir: Optional[Union[str, Path]] = None,
) -> Optional[AgentDefinition]:
    """Retrieve an agent definition by name considering discovery precedence."""
    all_agents = discover_agents(project_root=project_root, home_dir=home_dir)
    return all_agents.get(name)


def list_agents(
    project_root: Optional[Union[str, Path]] = None,
    home_dir: Optional[Union[str, Path]] = None,
) -> List[AgentDefinition]:
    """Return all discovered agents sorted by name."""
    all_agents = discover_agents(project_root=project_root, home_dir=home_dir)
    return [all_agents[k] for k in sorted(all_agents.keys())]
