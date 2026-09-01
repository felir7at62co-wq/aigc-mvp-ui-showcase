"""
AIGC Pipeline — LLM API 客户端

由原镜头提示词客户端演进而来
使用 OpenAI Python SDK 支持兼容接口（火山引擎等）。
"""
import os
import re
import time
import base64
import logging
import functools
import threading
from typing import List, Optional, Generator

from openai import OpenAI

from core.llm_cache import LLMCache

logger = logging.getLogger(__name__)

# Phase 3.1: 共享 LLM 客户端实例
_shared_llm_client = None
_shared_llm_client_config = None
_shared_llm_client_lock = threading.Lock()


def get_shared_llm_client(
    api_key: str, base_url: str, model: str,
    max_tokens: int = 4096, temperature: float = 0.7,
    use_cache: bool = True, cache_path: Optional[str] = None,
) -> "LLMClient":
    """获取共享 LLM 客户端实例（线程安全）。

    key 由 (api_key, base_url, model, max_tokens, temperature, use_cache, cache_path) 构成。
    当配置参数变化时自动创建新实例并用新实例替换旧实例（旧实例由 GC 回收）。
    """
    global _shared_llm_client, _shared_llm_client_config

    config_key = (api_key, base_url, model, max_tokens, temperature, use_cache, cache_path)

    with _shared_llm_client_lock:
        if _shared_llm_client is not None and _shared_llm_client_config == config_key:
            from core.perf_stats import perf_counter
            perf_counter["llm_client_reuse"].hit()
            return _shared_llm_client

        from core.perf_stats import perf_counter
        perf_counter["llm_client_reuse"].miss()
        _shared_llm_client = LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            use_cache=use_cache,
            cache_path=cache_path,
        )
        _shared_llm_client_config = config_key
        return _shared_llm_client


def reset_shared_llm_client():
    """重置共享客户端（测试用，强制执行下次调用时重新创建）。"""
    global _shared_llm_client, _shared_llm_client_config
    with _shared_llm_client_lock:
        _shared_llm_client = None
        _shared_llm_client_config = None


def _is_placeholder_api_key(api_key: str) -> bool:
    """Treat the copied .env.example value as missing, not as a real key."""
    value = str(api_key or "").strip().lower()
    if not value:
        return True
    return value.startswith((
        "your_", "your-", "placeholder", "xxx", "填入", "你的", "<your",
    ))


# ========== 工具函数 ==========

def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0,
                       max_delay: float = 60.0):
    """
    指数退避重试装饰器。

    重试: 网络超时、API 限流(429)、服务端错误(5xx)
    不重试: 认证失败(401/403)、参数错误(400)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_msg = str(e).lower()
                    non_retryable = [
                        "401", "403", "invalid_api_key",
                        "authentication", "forbidden",
                    ]
                    if any(code in error_msg for code in non_retryable):
                        logger.error(f"不可重试的错误: {e}")
                        raise
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            f"请求失败 (第{attempt + 1}次), "
                            f"{delay:.1f}秒后重试: {e}"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"已达最大重试次数({max_retries}): {e}")
            raise last_exception
        return wrapper
    return decorator


def estimate_tokens(text: str) -> int:
    """
    粗略估算中文文本的 token 数。

    中文: ~1.5 token/字符
    英文: ~0.75 token/word
    """
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    en_words = len(re.findall(r"[a-zA-Z]+", text))
    punctuation = len(re.findall(r"[^\w\s]", text))
    return int(cn_chars * 1.5 + en_words * 0.75 + punctuation * 0.5 + 10)


# ========== LLM 客户端 ==========

class LLMClient:
    """
    OpenAI 兼容 API 客户端

    支持火山引擎 Ark、OpenAI、DeepSeek 等兼容接口。
    """

    def __init__(self, api_key: str, base_url: str, model: str,
                 max_tokens: int = 4096, temperature: float = 0.7,
                 timeout: int = 120, use_cache: bool = True,
                 cache_path: Optional[str] = None):
        if _is_placeholder_api_key(api_key):
            raise ValueError(
                "LLM API Key 未配置或仍是示例占位符。"
                "请在程序设置中填写真实的 LLM_API_KEY 后再提取提示词。"
            )

        # Phase 0.3: 禁网模式 guard — 测试/loop 时防止意外触发真实 API
        if os.environ.get("AIGC_DISABLE_NETWORK"):
            raise RuntimeError(
                "AIGC_DISABLE_NETWORK 已设置，禁止初始化 LLM 客户端。"
            )

        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.use_cache = use_cache

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

        # 累计 token 用量统计
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0

        # 初始化缓存
        if use_cache:
            self.cache = LLMCache(cache_path) if cache_path else LLMCache()
        else:
            self.cache = None

        logger.info(f"LLM 客户端初始化: model={model}, base_url={base_url}, use_cache={use_cache}")

    @classmethod
    def from_config(cls, llm_config, use_cache: bool = True, cache_path: Optional[str] = None) -> "LLMClient":
        """从 LLMConfig 创建实例"""
        return cls(
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            model=llm_config.model,
            max_tokens=llm_config.max_tokens,
            temperature=llm_config.temperature,
            timeout=llm_config.timeout,
            use_cache=use_cache,
            cache_path=cache_path,
        )

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def generate(
        self,
        messages: List[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        use_cache: Optional[bool] = None,
    ) -> str:
        """
        调用 chat/completions 生成文本。

        参数:
            messages: [{"role": "system"|"user", "content": "..."}]
            max_tokens: 最大输出 token 数
            temperature: 生成温度
            use_cache: 是否使用缓存（默认继承自类属性）

        返回:
            生成的文本内容
        """
        # 确定是否使用缓存
        use_cache = use_cache if use_cache is not None else self.use_cache

        # 计算 prompt 哈希用于缓存查找
        if use_cache and self.cache is not None:
            prompt_text = "\n".join([msg["content"] for msg in messages])
            cached_response = self.cache.get(prompt_text, self.model)
            if cached_response is not None:
                logger.debug("LLM 响应从缓存获取")
                self.total_requests += 1
                # 估算 token 用量（因为从缓存获取，无法准确统计）
                estimated_tokens = estimate_tokens(prompt_text)
                self.total_prompt_tokens += estimated_tokens
                self.total_completion_tokens += estimate_tokens(cached_response)
                return cached_response

        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None
                          else self.temperature,
        }

        logger.info(
            f"LLM 请求: model={self.model}, "
            f"messages={len(messages)}, "
            f"max_tokens={params['max_tokens']}"
        )

        response = self.client.chat.completions.create(**params)
        content = response.choices[0].message.content

        # 累计 token 用量
        self.total_requests += 1
        usage_info = ""
        if response.usage:
            self.total_prompt_tokens += response.usage.prompt_tokens or 0
            self.total_completion_tokens += response.usage.completion_tokens or 0
            usage_info = (
                f", tokens: prompt={response.usage.prompt_tokens}, "
                f"completion={response.usage.completion_tokens}, "
                f"total={response.usage.total_tokens}"
            )
        logger.info(f"LLM 响应: {len(content)} 字符{usage_info}")

        # 缓存响应
        if use_cache and self.cache is not None:
            prompt_text = "\n".join([msg["content"] for msg in messages])
            self.cache.set(prompt_text, content, self.model)

        return content

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def generate_with_tools(
        self,
        messages: List[dict],
        tools: List[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        """带工具定义的 chat/completions 调用（function calling）。

        如果模型不支持 function calling，则降级到带有工具描述的纯文本解析。
        """
        try:
            params = {
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "max_tokens": max_tokens or self.max_tokens,
                "temperature": temperature if temperature is not None
                              else self.temperature,
            }
            logger.info(
                f"LLM tool-use 请求: model={self.model}, "
                f"messages={len(messages)}, tools={len(tools)}"
            )
            response = self.client.chat.completions.create(**params)
            self.total_requests += 1
            if response.usage:
                self.total_prompt_tokens += response.usage.prompt_tokens or 0
                self.total_completion_tokens += response.usage.completion_tokens or 0
            return response
        except Exception as e:
            logger.warning(f"Function calling 失败，降级到纯文本解析: {e}")
            return self._fallback_to_text_parsing(messages, tools, max_tokens, temperature)

    def _fallback_to_text_parsing(
        self,
        messages: List[dict],
        tools: List[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        """降级方案：将工具信息转换为文本描述添加到 prompt 中"""

        # 生成工具描述文本
        tool_descriptions = []
        for tool in tools:
            tool_descriptions.append(f"\n## 工具: {tool['function']['name']}")
            tool_descriptions.append(f"描述: {tool['function']['description']}")
            tool_descriptions.append("参数:")
            params = tool['function']['parameters']
            if 'properties' in params:
                for param_name, param_info in params['properties'].items():
                    required = " (必填)" if param_name in params.get('required', []) else ""
                    param_desc = param_info.get('description', "")
                    tool_descriptions.append(f"  - {param_name}{required}: {param_desc}")

        tool_text = "\n".join(tool_descriptions)

        # 创建新的 messages，包含工具描述
        fallback_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                # 增强系统提示词，添加工具信息
                fallback_msg = msg.copy()
                fallback_msg['content'] += (
                    "\n\n你现在可以通过文本解析的方式调用工具，格式如下：\n"
                    "<TOOLCALL>\n"
                    "- tool: <工具名>\n"
                    "- args: {参数JSON}\n"
                    "</TOOLCALL>\n\n"
                    "工具列表：" + tool_text
                )
                fallback_messages.append(fallback_msg)
            else:
                fallback_messages.append(msg.copy())

        # 调用普通 generate 方法
        text_response = self.generate(fallback_messages, max_tokens, temperature)

        # 模拟 OpenAI API 响应结构
        class FallbackMessage:
            content = text_response
            tool_calls = None

        class FallbackChoice:
            finish_reason = "stop"
            message = FallbackMessage()

        class FallbackResponse:
            choices = [FallbackChoice()]
            usage = None

        return FallbackResponse()

    def stream_generate(
        self,
        messages: List[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Generator[str, None, None]:
        """流式输出"""
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None
                          else self.temperature,
            "stream": True,
        }
        stream = self.client.chat.completions.create(**params)
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def health_check(self) -> bool:
        """API 健康检查"""
        try:
            resp = self.generate(
                messages=[{"role": "user", "content": "请回复ok"}],
                max_tokens=10,
            )
            return "ok" in resp.lower()
        except Exception as e:
            logger.error(f"LLM 健康检查失败: {e}")
            return False

    def get_usage_stats(self) -> dict:
        """获取累计 token 用量统计"""
        total_tokens = self.total_prompt_tokens + self.total_completion_tokens
        return {
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": total_tokens,
        }

    def invalidate_cache(self, messages: List[dict]):
        """清除特定 prompt 的缓存（用于解析失败后强制重试）。"""
        if self.cache is not None:
            prompt_text = "\n".join([msg["content"] for msg in messages])
            self.cache.delete(prompt_text, self.model)

    def reset_usage_stats(self):
        """重置用量统计"""
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def generate_with_images(
        self,
        prompt: str,
        image_paths: List[str],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        发送带图片的请求（视觉 LLM）。

        使用 OpenAI 兼容的 image_url 格式，图片以 base64 编码内联。

        参数:
            prompt: 文本提示
            image_paths: 图片文件路径列表
            system_prompt: 系统提示词
            max_tokens: 最大输出 token 数
            temperature: 生成温度

        返回:
            LLM 生成的文本内容
        """
        MIME_TYPES = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }

        content = [{"type": "text", "text": prompt}]

        MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB, 留余量

        for img_path in image_paths:
            if not os.path.exists(img_path):
                logger.warning(f"图片不存在，跳过: {img_path}")
                continue

            ext = os.path.splitext(img_path)[1].lower()
            mime = MIME_TYPES.get(ext, "image/jpeg")

            file_size = os.path.getsize(img_path)
            if file_size > MAX_IMAGE_BYTES:
                logger.info(f"图片过大 ({file_size // 1024 // 1024}MB)，自动压缩: {img_path}")
                b64_data = self._resize_image_to_base64(img_path, MAX_IMAGE_BYTES)
                mime = "image/jpeg"
            else:
                with open(img_path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")

            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64_data}",
                },
            })

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})

        logger.info(
            f"LLM 视觉请求: model={self.model}, "
            f"images={len(image_paths)}, prompt_len={len(prompt)}"
        )

        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None
                          else self.temperature,
        }

        response = self.client.chat.completions.create(**params)
        result = response.choices[0].message.content or ""

        logger.info(f"LLM 视觉响应: {len(result)} 字符")
        return result

    @staticmethod
    def _resize_image_to_base64(img_path: str, max_bytes: int) -> str:
        """压缩图片至指定大小以内，返回 base64 编码"""
        from PIL import Image
        import io

        img = Image.open(img_path)
        if img.mode == "RGBA":
            img = img.convert("RGB")

        quality = 85
        for scale in [1.0, 0.75, 0.5, 0.35, 0.25]:
            w, h = int(img.width * scale), int(img.height * scale)
            resized = img.resize((w, h), Image.LANCZOS) if scale < 1.0 else img
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=quality)
            if buf.tell() <= max_bytes:
                return base64.b64encode(buf.getvalue()).decode("utf-8")
            quality = max(50, quality - 10)

        buf = io.BytesIO()
        img.resize((img.width // 4, img.height // 4), Image.LANCZOS).save(
            buf, format="JPEG", quality=50
        )
        return base64.b64encode(buf.getvalue()).decode("utf-8")
