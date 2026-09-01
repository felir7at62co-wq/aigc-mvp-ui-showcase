"""
文件操作工具封装
"""
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from core.tool_registry import ToolRegistry, ToolType, register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="file_read",
    tool_type=ToolType.FILE,
    description="读取文件内容",
    version="1.0.0",
    author="AIGC Pipeline Team",
    required_config=[],
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径"},
            "encoding": {"type": "string", "description": "文件编码", "default": "utf-8"},
            "max_lines": {"type": "integer", "description": "最大读取行数（可选）"},
            "offset": {"type": "integer", "description": "起始行偏移（可选）"}
        },
        "required": ["file_path"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "content": {"type": "string"},
            "lines": {"type": "integer"},
            "size": {"type": "integer"},
            "error": {"type": "string"}
        }
    }
)
def file_read(params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    读取文件内容

    参数:
        params: 工具参数
        config: 工具配置

    返回:
        包含文件内容的字典
    """
    try:
        file_path = Path(params["file_path"])
        encoding = params.get("encoding", "utf-8")

        if not file_path.exists():
            return {
                "success": False,
                "error": f"文件不存在: {file_path}"
            }

        with open(file_path, "r", encoding=encoding) as f:
            lines = f.readlines()

        # 处理行数限制
        max_lines = params.get("max_lines")
        offset = params.get("offset", 0)

        if offset > 0:
            lines = lines[offset:]
        if max_lines:
            lines = lines[:max_lines]

        return {
            "success": True,
            "content": "".join(lines),
            "lines": len(lines),
            "size": file_path.stat().st_size
        }
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool(
    name="file_write",
    tool_type=ToolType.FILE,
    description="写入文件内容",
    version="1.0.0",
    author="AIGC Pipeline Team",
    required_config=[],
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "文件内容"},
            "encoding": {"type": "string", "description": "文件编码", "default": "utf-8"},
            "append": {"type": "boolean", "description": "是否追加模式", "default": False},
            "create_dirs": {"type": "boolean", "description": "是否创建父目录", "default": True}
        },
        "required": ["file_path", "content"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "file_path": {"type": "string"},
            "bytes_written": {"type": "integer"},
            "error": {"type": "string"}
        }
    }
)
def file_write(params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    写入文件内容

    参数:
        params: 工具参数
        config: 工具配置

    返回:
        包含写入结果的字典
    """
    try:
        file_path = Path(params["file_path"])
        content = params["content"]
        encoding = params.get("encoding", "utf-8")
        append = params.get("append", False)
        create_dirs = params.get("create_dirs", True)

        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        with open(file_path, mode, encoding=encoding) as f:
            bytes_written = f.write(content)

        return {
            "success": True,
            "file_path": str(file_path),
            "bytes_written": bytes_written
        }
    except Exception as e:
        logger.error(f"写入文件失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool(
    name="file_list",
    tool_type=ToolType.FILE,
    description="列出目录内容",
    version="1.0.0",
    author="AIGC Pipeline Team",
    required_config=[],
    input_schema={
        "type": "object",
        "properties": {
            "dir_path": {"type": "string", "description": "目录路径"},
            "pattern": {"type": "string", "description": "文件匹配模式（可选）", "default": "*"},
            "recursive": {"type": "boolean", "description": "是否递归", "default": False},
            "include_dirs": {"type": "boolean", "description": "是否包含目录", "default": True}
        },
        "required": ["dir_path"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "files": {"type": "array", "items": {"type": "string"}},
            "directories": {"type": "array", "items": {"type": "string"}},
            "count": {"type": "integer"},
            "error": {"type": "string"}
        }
    }
)
def file_list(params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    列出目录内容

    参数:
        params: 工具参数
        config: 工具配置

    返回:
        包含目录内容的字典
    """
    try:
        dir_path = Path(params["dir_path"])
        pattern = params.get("pattern", "*")
        recursive = params.get("recursive", False)
        include_dirs = params.get("include_dirs", True)

        if not dir_path.exists():
            return {
                "success": False,
                "error": f"目录不存在: {dir_path}"
            }

        if not dir_path.is_dir():
            return {
                "success": False,
                "error": f"不是目录: {dir_path}"
            }

        files = []
        directories = []

        glob_pattern = f"**/{pattern}" if recursive else pattern
        for item in dir_path.glob(glob_pattern):
            if item.is_file():
                files.append(str(item))
            elif item.is_dir() and include_dirs:
                directories.append(str(item))

        return {
            "success": True,
            "files": files,
            "directories": directories,
            "count": len(files) + len(directories)
        }
    except Exception as e:
        logger.error(f"列出目录失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool(
    name="file_copy",
    tool_type=ToolType.FILE,
    description="复制文件或目录",
    version="1.0.0",
    author="AIGC Pipeline Team",
    required_config=[],
    input_schema={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "源路径"},
            "destination": {"type": "string", "description": "目标路径"},
            "overwrite": {"type": "boolean", "description": "是否覆盖", "default": False}
        },
        "required": ["source", "destination"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "source": {"type": "string"},
            "destination": {"type": "string"},
            "error": {"type": "string"}
        }
    }
)
def file_copy(params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    复制文件或目录

    参数:
        params: 工具参数
        config: 工具配置

    返回:
        包含复制结果的字典
    """
    try:
        source = Path(params["source"])
        destination = Path(params["destination"])
        overwrite = params.get("overwrite", False)

        if not source.exists():
            return {
                "success": False,
                "error": f"源路径不存在: {source}"
            }

        if destination.exists() and not overwrite:
            return {
                "success": False,
                "error": f"目标已存在: {destination}"
            }

        if source.is_file():
            shutil.copy2(source, destination)
        elif source.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)

        return {
            "success": True,
            "source": str(source),
            "destination": str(destination)
        }
    except Exception as e:
        logger.error(f"复制文件失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool(
    name="file_delete",
    tool_type=ToolType.FILE,
    description="删除文件或目录",
    version="1.0.0",
    author="AIGC Pipeline Team",
    required_config=[],
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要删除的路径"},
            "force": {"type": "boolean", "description": "强制删除目录（即使不为空）", "default": False}
        },
        "required": ["path"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "path": {"type": "string"},
            "error": {"type": "string"}
        }
    }
)
def file_delete(params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    删除文件或目录

    参数:
        params: 工具参数
        config: 工具配置

    返回:
        包含删除结果的字典
    """
    try:
        path = Path(params["path"])
        force = params.get("force", False)

        if not path.exists():
            return {
                "success": False,
                "error": f"路径不存在: {path}"
            }

        if path.is_file():
            path.unlink()
        elif path.is_dir():
            if force:
                shutil.rmtree(path)
            else:
                path.rmdir()

        return {
            "success": True,
            "path": str(path)
        }
    except Exception as e:
        logger.error(f"删除路径失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def register_tools(registry: ToolRegistry) -> int:
    """
    批量注册文件操作工具

    参数:
        registry: 工具注册器实例

    返回:
        已注册的工具数量
    """
    return 5
