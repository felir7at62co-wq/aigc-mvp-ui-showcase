"""
Skill 注册表 - 管理所有可用的 Skill
"""
import logging
from typing import Dict, Type, Optional, List
from pathlib import Path

from .base import Skill, SkillContext

logger = logging.getLogger(__name__)


class SkillRegistry:
    """
    Skill 注册表

    负责注册、发现和实例化 Skill
    """

    def __init__(self):
        self._skills: Dict[str, Type[Skill]] = {}

    def register(self, skill_class: Type[Skill]) -> Type[Skill]:
        """
        注册一个 Skill 类

        Args:
            skill_class: Skill 类

        Returns:
            注册的 Skill 类（用于装饰器）
        """
        name = skill_class.name
        if not name:
            name = skill_class.__name__
            logger.warning(f"Skill {skill_class.__name__} 没有设置 name，使用类名")

        self._skills[name] = skill_class
        logger.info(f"Skill '{name}' 已注册")
        return skill_class

    def get(self, name: str) -> Optional[Type[Skill]]:
        """获取 Skill 类"""
        return self._skills.get(name)

    def create(self, name: str, context: SkillContext) -> Optional[Skill]:
        """
        创建 Skill 实例

        Args:
            name: Skill 名称
            context: Skill 上下文

        Returns:
            Skill 实例，如果不存在则返回 None
        """
        skill_class = self.get(name)
        if not skill_class:
            logger.error(f"Skill '{name}' 未找到")
            return None
        return skill_class(context)

    def list_all(self) -> List[str]:
        """列出所有已注册的 Skill 名称"""
        return list(self._skills.keys())

    def list_with_info(self) -> List[Dict[str, str]]:
        """列出所有 Skill 的详细信息"""
        return [
            {
                "name": name,
                "description": skill.description,
                "version": skill.version,
                "dependencies": skill.dependencies,
            }
            for name, skill in self._skills.items()
        ]

    def load_skills_from_directory(self, directory: str = "core/skills") -> int:
        """
        从目录自动加载 Skill

        Args:
            directory: Skill 目录

        Returns:
            加载的 Skill 数量
        """
        import importlib.util
        import sys

        skills_dir = Path(directory)
        if not skills_dir.exists():
            logger.warning(f"Skill 目录不存在: {directory}")
            return 0

        loaded_count = 0

        for file_path in skills_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue

            try:
                # 动态加载模块
                module_name = f"core.skills.{file_path.stem}"
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    loaded_count += 1
                    logger.debug(f"已加载 Skill 模块: {file_path.name}")
            except Exception as e:
                logger.warning(f"加载 Skill 模块失败 {file_path.name}: {e}")

        return loaded_count


# 全局 Skill 注册表实例
_global_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取全局 Skill 注册表（单例）"""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry


def register_skill(skill_class: Type[Skill]) -> Type[Skill]:
    """
    Skill 装饰器 - 简化注册

    使用方式:
        @register_skill
        class MySkill(Skill):
            name = "my_skill"
            ...
    """
    registry = get_skill_registry()
    return registry.register(skill_class)
