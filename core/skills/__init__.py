"""
Skill 模块 - 定义工作流程

Skill = 工作流程编排
每个 Skill 封装一个完整的工作步骤，可以独立使用，也可以被 Pipeline 协调
"""
import os
from .base import Skill, SkillContext, SkillResult, SkillStatus
from .skill_registry import SkillRegistry, get_skill_registry

# 自动加载当前目录下的所有 Skill 模块
def _auto_load_skills():
    """自动发现并加载 skills 目录下的所有 Skill"""
    import importlib
    from pathlib import Path

    skills_dir = Path(__file__).parent
    loaded_count = 0

    for file_path in skills_dir.glob("*.py"):
        if file_path.name.startswith("_"):
            continue
        if file_path.name == "base.py" or file_path.name == "skill_registry.py":
            continue

        module_name = f"core.skills.{file_path.stem}"
        try:
            importlib.import_module(module_name)
            loaded_count += 1
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"自动加载 Skill 失败 {file_path.name}: {e}"
            )

    return loaded_count

# 尝试自动加载
try:
    _loaded = _auto_load_skills()
except Exception:
    pass

__all__ = [
    "Skill",
    "SkillContext",
    "SkillResult",
    "SkillStatus",
    "SkillRegistry",
    "get_skill_registry",
]
