"""
LLM API 工具封装
"""
import logging
import time
from typing import Dict, Any, Optional, List
from core.tool_registry import ToolRegistry, ToolType, register_tool
from core import llm_client

logger = logging.getLogger(__name__)


@register_tool(
    name="llm_generate_text",
    tool_type=ToolType.LLM,
    description="调用 LLM 生成文本",
    version="1.0.0",
    author="AIGC Pipeline Team",
    required_config=["api_key", "base_url", "model"],
    input_schema={
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["role", "content"]
                },
                "description": "对话历史"
            },
            "max_tokens": {"type": "integer", "description": "最大输出 token 数", "default": 4096},
            "temperature": {"type": "number", "description": "生成温度", "default": 0.7},
            "use_cache": {"type": "boolean", "description": "是否使用缓存", "default": True}
        },
        "required": ["messages"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "text": {"type": "string"},
            "token_usage": {
                "type": "object",
                "properties": {
                    "prompt_tokens": {"type": "integer"},
                    "completion_tokens": {"type": "integer"},
                    "total_tokens": {"type": "integer"}
                }
            },
            "error": {"type": "string"}
        }
    }
)
def llm_generate_text(params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    调用 LLM 生成文本

    参数:
        params: 工具参数
        config: 工具配置

    返回:
        包含生成结果的字典
    """
    try:
        # 创建 LLM 客户端
        client = llm_client.LLMClient(
            api_key=config["api_key"],
            base_url=config.get("base_url", "https://ark.cn-beijing.volces.com/api/coding/v3"),
            model=config.get("model", "ark-code-latest")
        )

        # 调用 LLM 生成
        start_time = time.time()
        text = client.generate(
            params["messages"],
            params.get("max_tokens", 4096),
            params.get("temperature", 0.7),
            params.get("use_cache", True)
        )
        end_time = time.time()

        # 获取使用统计
        usage = client.get_usage_stats()

        return {
            "success": True,
            "text": text,
            "token_usage": {
                "prompt_tokens": usage["total_prompt_tokens"],
                "completion_tokens": usage["total_completion_tokens"],
                "total_tokens": usage["total_tokens"]
            },
            "time_ms": (end_time - start_time) * 1000
        }
    except Exception as e:
        logger.error(f"LLM 文本生成失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool(
    name="llm_generate_with_images",
    tool_type=ToolType.LLM,
    description="调用视觉 LLM 处理图文内容",
    version="1.0.0",
    author="AIGC Pipeline Team",
    required_config=["api_key", "base_url", "model"],
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "文本提示"},
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "图像文件路径列表"
            },
            "system_prompt": {"type": "string", "description": "系统提示词", "default": ""},
            "max_tokens": {"type": "integer", "description": "最大输出 token 数", "default": 4096},
            "temperature": {"type": "number", "description": "生成温度", "default": 0.7}
        },
        "required": ["prompt", "image_paths"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "text": {"type": "string"},
            "token_usage": {
                "type": "object",
                "properties": {
                    "prompt_tokens": {"type": "integer"},
                    "completion_tokens": {"type": "integer"},
                    "total_tokens": {"type": "integer"}
                }
            },
            "error": {"type": "string"}
        }
    }
)
def llm_generate_with_images(params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    调用视觉 LLM 处理图文内容

    参数:
        params: 工具参数
        config: 工具配置

    返回:
        包含生成结果的字典
    """
    try:
        client = llm_client.LLMClient(
            api_key=config["api_key"],
            base_url=config.get("base_url"),
            model=config.get("model")
        )

        text = client.generate_with_images(
            params["prompt"],
            params["image_paths"],
            params.get("system_prompt", ""),
            params.get("max_tokens"),
            params.get("temperature")
        )

        usage = client.get_usage_stats()

        return {
            "success": True,
            "text": text,
            "token_usage": {
                "prompt_tokens": usage["total_prompt_tokens"],
                "completion_tokens": usage["total_completion_tokens"],
                "total_tokens": usage["total_tokens"]
            }
        }
    except Exception as e:
        logger.error(f"LLM 图文处理失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool(
    name="llm_health_check",
    tool_type=ToolType.LLM,
    description="检查 LLM API 健康状态",
    version="1.0.0",
    author="AIGC Pipeline Team",
    required_config=["api_key", "base_url", "model"],
    input_schema={
        "type": "object",
        "properties": {}
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "healthy": {"type": "boolean"},
            "response_time": {"type": "number"},
            "error": {"type": "string"}
        }
    }
)
def llm_health_check(params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    检查 LLM API 健康状态

    参数:
        params: 工具参数
        config: 工具配置

    返回:
        包含健康检查结果的字典
    """
    try:
        client = llm_client.LLMClient(
            api_key=config["api_key"],
            base_url=config.get("base_url"),
            model=config.get("model")
        )

        start_time = time.time()
        healthy = client.health_check()
        response_time = (time.time() - start_time) * 1000

        return {
            "success": True,
            "healthy": healthy,
            "response_time": response_time
        }
    except Exception as e:
        logger.error(f"LLM 健康检查失败: {e}")
        return {
            "success": False,
            "healthy": False,
            "error": str(e)
        }


def register_tools(registry: ToolRegistry) -> int:
    """
    批量注册 LLM 工具

    参数:
        registry: 工具注册器实例

    返回:
        已注册的工具数量
    """
    return 3
