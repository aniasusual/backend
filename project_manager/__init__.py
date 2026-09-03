"""
Lowkey Project Manager — Manages user projects under ~/.lowkey/projects/.

Usage:
    from project_manager import ProjectManager, ProjectInfo

    pm = ProjectManager()
    project = pm.create_project("todo-app")
    projects = pm.list_projects()
"""

from project_manager.models import ProjectInfo
from project_manager.manager import ProjectManager
from project_manager.chat_history import ChatHistoryManager

__all__ = ["ProjectManager", "ProjectInfo", "ChatHistoryManager"]
