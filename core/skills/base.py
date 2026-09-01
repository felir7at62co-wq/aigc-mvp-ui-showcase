"""
Skill 基类 - 定义 Skill 的标准接口
"""
import os
import logging
import time
from enum import Enum
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillStatus(Enum):
    """Skill 执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SkillContext:
    """
    Skill 执行上下文

    提供 Skill 执行所需的环境信息和共享数据
    """
    project_dir: str  # 项目根目录
    config: Dict[str, Any] = field(default_factory=dict)  # 配置
    shared_data: Dict[str, Any] = field(default_factory=dict)  # 共享数据
    on_progress: Optional[Callable[[int, int, str], None]] = None  # 进度回调

    def get_step_dir(self, step_name: str) -> str:
        """获取步骤输出目录"""
        dir_path = os.path.join(self.project_dir, step_name)
        os.makedirs(dir_path, exist_ok=True)
        return dir_path

    def get_asset_dir(self, asset_type: str) -> str:
        """获取资产目录"""
        dir_path = os.path.join(self.project_dir, "assets", asset_type)
        os.makedirs(dir_path, exist_ok=True)
        return dir_path


@dataclass
class SkillResult:
    """
    Skill 执行结果
    """
    success: bool
    status: SkillStatus
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    elapsed: float = 0.0
    output_count: int = 0

    @classmethod
    def success(cls, message: str = "", data: Dict[str, Any] = None, output_count: int = 0) -> "SkillResult":
        """创建成功结果"""
        return cls(
            success=True,
            status=SkillStatus.COMPLETED,
            message=message,
            data=data or {},
            output_count=output_count,
        )

    @classmethod
    def failure(cls, error: str, message: str = "") -> "SkillResult":
        """创建失败结果"""
        return cls(
            success=False,
            status=SkillStatus.FAILED,
            message=message,
            error=error,
        )

    @classmethod
    def skipped(cls, message: str = "已完成，跳过") -> "SkillResult":
        """创建跳过结果"""
        return cls(
            success=True,
            status=SkillStatus.SKIPPED,
            message=message,
        )


class Skill:
    """
    Skill 基类

    每个 Skill 代表一个完整的工作步骤，负责：
    1. 定义该步骤的输入输出
    2. 编排该步骤需要的 Tools
    3. 执行该步骤的工作流程
    """

    # Skill 元数据
    name: str = ""  # Skill 名称（唯一标识）
    description: str = ""  # Skill 描述
    version: str = "1.0.0"  # 版本
    dependencies: List[str] = field(default_factory=list)  # 依赖的 Skill 列表

    def __init__(self, context: SkillContext):
        """
        初始化 Skill

        Args:
            context: Skill 执行上下文
        """
        self.context = context

    def can_skip(self) -> bool:
        """
        检查是否可以跳过该步骤（已完成时）

        Returns:
            True 表示可以跳过
        """
        return False

    def execute(self, params: Dict[str, Any] = None) -> SkillResult:
        """
        执行 Skill

        Args:
            params: Skill 参数

        Returns:
            SkillResult 执行结果
        """
        params = params or {}
        start_time = time.time()

        logger.info(f"[Skill:{self.name}] 开始执行")

        try:
            # 检查是否可以跳过
            if self.can_skip():
                logger.info(f"[Skill:{self.name}] 已完成，跳过")
                return SkillResult.skipped()

            # 执行具体逻辑
            result = self._run(params)

            # 记录耗时
            result.elapsed = time.time() - start_time

            if result.success:
                logger.info(f"[Skill:{self.name}] 完成: {result.message}")
            else:
                logger.error(f"[Skill:{self.name}] 失败: {result.error}")

            return result

        except Exception as e:
            logger.exception(f"[Skill:{self.name}] 异常")
            return SkillResult.failure(
                error=str(e),
                message=f"执行异常: {self.name}"
            )

    def _run(self, params: Dict[str, Any]) -> SkillResult:
        """
        Skill 的具体实现，子类需要覆盖此方法

        Args:
            params: Skill 参数

        Returns:
            SkillResult 执行结果
        """
        raise NotImplementedError("子类需要实现 _run 方法")

    def _report_progress(self, current: int, total: int, detail: str = ""):
        """报告进度"""
        if self.context.on_progress:
            self.context.on_progress(current, total, detail)
