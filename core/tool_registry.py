"""
AIGC 工具注册器 - 统一管理和调用所有 AIGC 工具
参考了 claw-code-main/src/tools.py 的设计理念
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Type, Any, Optional, List, Callable, Protocol, runtime_checkable
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolType(Enum):
    """工具类型枚举"""
    LLM = "llm"                # LLM 调用工具
    FILE = "file"              # 文件操作工具
    VIDEO = "video"            # 视频生成工具
    IMAGE = "image"            # 图像处理工具


@runtime_checkable
class ToolInterface(Protocol):
    """标准工具接口定义"""

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        ...

    def get_metadata(self) -> 'ToolMetadata':
        """获取工具元数据"""
        ...

    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """验证参数，返回错误列表（空列表表示验证通过）"""
        ...


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str  # 'string', 'number', 'boolean', 'array', 'object'
    required: bool = True
    description: str = ""
    default: Any = None
    enum: List[Any] = field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None


@dataclass
class ToolUsageStats:
    """工具使用统计"""
    tool_name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0
    last_call_time: Optional[float] = None


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    tool_type: ToolType
    description: str
    version: str
    author: str = ""
    required_config: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    parameters: List[ToolParameter] = field(default_factory=list)  # 替代 input_schema
    examples: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class ToolInstance:
    """工具实例"""
    metadata: ToolMetadata
    implementation: Any
    config: Dict[str, Any]
    usage_stats: ToolUsageStats = field(default_factory=lambda: ToolUsageStats(tool_name=""))


class ToolRegistry:
    """AIGC 工具注册器"""

    def __init__(self, tools_dir: str = "core/tools"):
        self.tools_dir = Path(tools_dir)
        self.tools_dir.mkdir(exist_ok=True)
        self._tools: Dict[str, ToolInstance] = {}
        self._tool_combinations: Dict[str, List[str]] = {}

    def register_tool(
        self,
        metadata: ToolMetadata,
        implementation: Any,
        default_config: Dict[str, Any] = None
    ):
        """注册工具"""
        instance = ToolInstance(
            metadata=metadata,
            implementation=implementation,
            config=default_config or {},
            usage_stats=ToolUsageStats(tool_name=metadata.name)
        )
        self._tools[metadata.name] = instance
        logger.info(f"工具 '{metadata.name}' 注册成功")
        return instance

    def get_tool(self, name: str) -> Optional[ToolInstance]:
        """获取工具实例"""
        return self._tools.get(name)

    def list_all_tools(self) -> List[ToolInstance]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_tools_by_type(self, tool_type: ToolType) -> List[ToolInstance]:
        """按类型列出工具"""
        return [
            tool for tool in self._tools.values()
            if tool.metadata.tool_type == tool_type
        ]

    def validate_tool_params(self, tool: ToolInstance, params: Dict[str, Any]) -> List[str]:
        """验证工具参数"""
        errors = []

        # 检查必需参数
        for param in tool.metadata.parameters:
            if param.required and param.name not in params:
                errors.append(f"缺少必需参数: {param.name}")
                continue

            if param.name in params:
                value = params[param.name]

                # 类型检查
                if param.type == "string" and not isinstance(value, str):
                    errors.append(f"参数 '{param.name}' 类型错误，应是字符串")
                elif param.type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"参数 '{param.name}' 类型错误，应是数字")
                elif param.type == "boolean" and not isinstance(value, bool):
                    errors.append(f"参数 '{param.name}' 类型错误，应是布尔值")
                elif param.type == "array" and not isinstance(value, list):
                    errors.append(f"参数 '{param.name}' 类型错误，应是数组")
                elif param.type == "object" and not isinstance(value, dict):
                    errors.append(f"参数 '{param.name}' 类型错误，应是对象")

                # 数值范围检查
                if param.type == "number":
                    if param.min_value is not None and value < param.min_value:
                        errors.append(f"参数 '{param.name}' 小于最小值 {param.min_value}")
                    if param.max_value is not None and value > param.max_value:
                        errors.append(f"参数 '{param.name}' 大于最大值 {param.max_value}")

                # 长度检查
                if param.type == "string":
                    if param.min_length is not None and len(value) < param.min_length:
                        errors.append(f"参数 '{param.name}' 长度小于最小值 {param.min_length}")
                    if param.max_length is not None and len(value) > param.max_length:
                        errors.append(f"参数 '{param.name}' 长度大于最大值 {param.max_length}")

                # 枚举值检查
                if param.enum and value not in param.enum:
                    errors.append(f"参数 '{param.name}' 值不在允许范围内: {', '.join(str(x) for x in param.enum)}")

        # 检查额外参数（可选，根据需求）
        # for param_name in params:
        #     if param_name not in [p.name for p in tool.metadata.parameters]:
        #         errors.append(f"未知参数: {param_name}")

        return errors

    def execute_tool(
        self,
        name: str,
        params: Dict[str, Any],
        config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """执行工具"""
        tool = self.get_tool(name)
        if not tool:
            return {
                "success": False,
                "error": f"未知工具: {name}"
            }

        # 更新统计数据 - 总调用次数
        tool.usage_stats.total_calls += 1
        start_time = time.time()

        try:
            # 合并配置
            merged_config = {**tool.config, **(config or {})}

            # 验证必需的配置
            missing_config = [
                key for key in tool.metadata.required_config
                if key not in merged_config
            ]
            if missing_config:
                tool.usage_stats.failed_calls += 1
                return {
                    "success": False,
                    "error": f"缺少必需配置: {', '.join(missing_config)}"
                }

            # 验证参数
            param_errors = self.validate_tool_params(tool, params)
            if param_errors:
                tool.usage_stats.failed_calls += 1
                return {
                    "success": False,
                    "error": "参数验证失败: " + "; ".join(param_errors)
                }

            # 执行工具
            if isinstance(tool.implementation, ToolInterface):
                result = tool.implementation.execute(params)
            else:
                # 支持函数式实现
                result = tool.implementation(params, merged_config)

            # 更新成功统计
            tool.usage_stats.successful_calls += 1
            execution_time = time.time() - start_time
            tool.usage_stats.total_execution_time += execution_time
            tool.usage_stats.avg_execution_time = (
                tool.usage_stats.total_execution_time / tool.usage_stats.successful_calls
            )
            tool.usage_stats.last_call_time = time.time()

            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            logger.error(f"工具执行失败 ({name}): {e}")
            tool.usage_stats.failed_calls += 1
            return {
                "success": False,
                "error": str(e)
            }

    def get_tool_usage_stats(self, name: str) -> Optional[ToolUsageStats]:
        """获取工具使用统计"""
        tool = self.get_tool(name)
        return tool.usage_stats if tool else None

    def get_all_usage_stats(self) -> Dict[str, ToolUsageStats]:
        """获取所有工具的使用统计"""
        return {
            tool.metadata.name: tool.usage_stats
            for tool in self._tools.values()
        }

    def reset_usage_stats(self, name: str = None):
        """重置工具使用统计"""
        if name:
            tool = self.get_tool(name)
            if tool:
                tool.usage_stats = ToolUsageStats(tool_name=name)
        else:
            for tool in self._tools.values():
                tool.usage_stats = ToolUsageStats(tool_name=tool.metadata.name)

    def load_tools_from_directory(self) -> int:
        """从目录加载工具（自动发现）"""
        loaded_count = 0

        if not self.tools_dir.exists():
            return loaded_count

        for tool_file in self.tools_dir.glob("*.py"):
            if tool_file.name.startswith("_"):
                continue

            # 尝试从工具文件中加载工具
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    f"core.tools.{tool_file.stem}",
                    str(tool_file)
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # 查找模块中的工具注册函数
                    if hasattr(module, "register_tools"):
                        count = module.register_tools(self)
                        loaded_count += count
                        logger.info(f"从 {tool_file.name} 加载了 {count} 个工具")
            except Exception as e:
                logger.warning(f"加载工具文件失败 ({tool_file.name}): {e}")

        return loaded_count


# 全局工具注册器实例
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册器（单例模式）"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def register_tool(
    name: str,
    tool_type: ToolType,
    description: str,
    version: str = "1.0.0",
    author: str = "",
    required_config: List[str] = None,
    input_schema: Dict[str, Any] = None,
    output_schema: Dict[str, Any] = None
):
    """工具装饰器 - 简化工具注册"""
    def decorator(func):
        registry = get_tool_registry()
        metadata = ToolMetadata(
            name=name,
            tool_type=tool_type,
            description=description,
            version=version,
            author=author,
            required_config=required_config or [],
            input_schema=input_schema or {},
            output_schema=output_schema or {}
        )
        registry.register_tool(metadata, func)
        return func
    return decorator
