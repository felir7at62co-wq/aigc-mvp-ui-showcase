"""
AIGC Pipeline — 统一配置加载器

优先级: 环境变量(.env) > config.yaml > 默认值

仅保留当前 Web 工作台所需的 LLM、云映媒体、资产与工具配置。
"""
import os
import re
import sys
import copy
import yaml
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple, Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Phase 2.1: 模块级 Config 缓存 — key=(abspath, mtime)，save_config 时失效
_config_cache: dict[str, tuple[float, "PipelineConfig"]] = {}


@dataclass
class YunyingMediaConfig:
    """云映 OpenAI 兼容图片/视频 API 配置。"""
    api_key: str = ""
    base_url: str = "https://wy6688.token6688.com/v1"
    video_model: str = "seedance-2-0-official"
    image_model: str = "gpt-image-2-official"
    timeout: int = 4500
    poll_interval: int = 5
    request_timeout: int = 120


@dataclass
class LLMConfig:
    """LLM API 配置（OpenAI 兼容）"""
    api_key: str = ""
    base_url: str = "https://ark.cn-beijing.volces.com/api/coding/v3"
    model: str = "ark-code-latest"
    max_tokens: int = 4096
    context_window: int = 32000
    temperature: float = 0.7
    timeout: int = 120
    use_cache: bool = True  # 是否启用 LLM 响应缓存
    cache_path: str = ""  # 缓存数据库路径（空字符串使用默认路径）


@dataclass
class AssetConfig:
    """资产生成配置"""
    max_input_chars: int = 20000         # LLM 提取资产描述时剧本文本截取上限
    prompt_node_id: str = "2"            # ComfyUI 工作流中提示词节点 ID
    character_template_path: str = ""    # 角色提取专用提示词模板路径
    scene_template_path: str = ""        # 场景提取专用提示词模板路径
    prop_template_path: str = ""         # 道具提取专用提示词模板路径
    selector_template_path: str = ""     # 生成前 LLM 分析选择提示词模板路径


@dataclass
class FilterOptions:
    text_filter_enabled: bool = True
    """内容过滤选项"""
    filter_episode_title: bool = True
    filter_colon_title: bool = False
    filter_version: bool = True
    filter_next_episode: bool = True
    filter_word_heading: bool = False
    filter_large_font: bool = False
    filter_short_bold: bool = False
    filter_bracket_title: bool = False
    filter_table_content: bool = False


@dataclass
class PipelineConfig:
    """Pipeline 全局配置"""
    media: YunyingMediaConfig = field(default_factory=YunyingMediaConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    asset: AssetConfig = field(default_factory=AssetConfig)
    filter_options: FilterOptions = field(default_factory=FilterOptions)
    project_root: str = "./projects"
    prompt_templates: Dict[str, str] = field(default_factory=dict)
    prompt_template_path: str = "./prompts/default_shot_prompt.txt"
    asset_template_path: str = "./prompts/default_asset_prompt.txt"
    log_level: str = "INFO"
    max_episodes: int = 999              # 默认最大集数上限

    # 外部工具路径
    draft_output_dir: str = ""
    ffmpeg_path: str = ""   # FFmpeg 可执行文件路径（留空则使用项目内置 tools/ffmpeg/ffmpeg.exe）
    jianying_path: str = "" # 剪映专业版路径（留空则自动检测默认安装位置）


def load_config(
    config_path: str = "config.yaml",
    env_path: str = ".env",
    base_dir: Optional[str] = None,
) -> PipelineConfig:
    """
    加载 Pipeline 配置。

    优先级: 环境变量(.env) > config.yaml > 默认值

    参数:
        config_path: config.yaml 路径（相对或绝对）
        env_path: .env 路径
        base_dir: 基准目录（默认为当前工作目录）

    返回:
        PipelineConfig 实例
    """
    cfg = PipelineConfig()
    from core.paths import (
        get_app_dir,
        get_config_path,
        get_data_dir,
        get_user_config_path,
    )
    base = base_dir or get_app_dir()

    # 解析绝对路径
    if not os.path.isabs(config_path):
        config_path = os.path.join(base, config_path)

    # In a frozen portable build, the bundled config is read-only. Every
    # worker may still pass that bundled path, so transparently prefer the
    # user override saved by the settings page.
    if getattr(sys, "frozen", False):
        bundled_path = os.path.abspath(get_config_path())
        if os.path.abspath(config_path) == bundled_path:
            user_config_path = get_user_config_path()
            if os.path.isfile(user_config_path):
                config_path = user_config_path

    # Phase 2.1: config 缓存 — key=(abspath, mtime)，save_config 时失效
    try:
        resolved_path = os.path.abspath(config_path)
        mtime = os.path.getmtime(resolved_path)
        cached_mtime, cached_cfg = _config_cache.get(resolved_path, (None, None))
        if cached_mtime == mtime and cached_cfg is not None:
            from core.perf_stats import perf_counter
            perf_counter["config_cache"].hit()
            return copy.deepcopy(cached_cfg)
    except OSError:
        pass

    from core.perf_stats import perf_counter
    perf_counter["config_cache"].miss()

    # 1. 加载 .env（优先使用 exe 旁的用户 .env，再回退到应用目录）
    if not os.path.isabs(env_path):
        env_path = os.path.join(base, env_path)
    user_env = os.path.join(get_data_dir(), ".env")
    if getattr(sys, "frozen", False) and os.path.exists(user_env):
        load_dotenv(user_env, override=True)
        logger.info(f"已加载 .env: {user_env}")
    elif os.path.exists(env_path):
        load_dotenv(env_path, override=True)
        logger.info(f"已加载 .env: {env_path}")

    # 2. 加载 config.yaml
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            _merge_yaml(cfg, raw)
            logger.info(f"已加载配置: {config_path}")
        except Exception as e:
            logger.warning(f"配置文件加载失败 ({config_path}): {e}")
    else:
        logger.info(f"配置文件不存在 ({config_path})，使用默认配置")

    # 3. 环境变量覆盖（最高优先级）
    _apply_env_overrides(cfg)

    # 4. 解析相对路径为绝对路径
    _resolve_paths(cfg, base)

    # 5. 验证必要配置
    _validate_config(cfg, env_path)

    # Phase 2.1: 写入缓存（含默认配置情形）；返回 deepcopy 防共享变异
    try:
        _config_cache[os.path.abspath(config_path)] = (
            os.path.getmtime(config_path) if os.path.exists(config_path) else 0,
            cfg,
        )
    except OSError:
        pass

    return copy.deepcopy(cfg)


def _config_to_dict(cfg: PipelineConfig) -> dict:
    """将 PipelineConfig 转为与 config.yaml 结构一致的嵌套 dict。"""

    def _dc(obj, keys):
        return {k: getattr(obj, k) for k in keys}

    data = {
        "media": _dc(cfg.media, [
            "base_url", "video_model", "image_model", "timeout",
            "poll_interval", "request_timeout",
        ]),
        "llm": _dc(cfg.llm, [
            "api_key", "base_url", "model", "max_tokens",
            "context_window", "temperature", "timeout",
        ]),
        "project": {"root": cfg.project_root},
        "filter_options": _dc(cfg.filter_options, [
            "text_filter_enabled",
            "filter_episode_title", "filter_colon_title",
            "filter_version", "filter_next_episode",
            "filter_word_heading", "filter_large_font",
            "filter_short_bold", "filter_bracket_title",
            "filter_table_content",
        ]),
        "prompt": {"template_path": cfg.prompt_template_path},
        "asset": {
            "template_path": cfg.asset_template_path,
            "character_template_path": cfg.asset.character_template_path,
            "scene_template_path": cfg.asset.scene_template_path,
            "prop_template_path": cfg.asset.prop_template_path,
            "selector_template_path": cfg.asset.selector_template_path,
            "max_input_chars": cfg.asset.max_input_chars,
            "prompt_node_id": cfg.asset.prompt_node_id,
            "max_quality_retries": 2,
        },
        "pipeline": {"max_episodes": cfg.max_episodes},
        "tools": {"ffmpeg_path": cfg.ffmpeg_path},
        "logging": {"level": cfg.log_level, "file": ""},
    }
    return data


def save_config(cfg: PipelineConfig, config_path: str = "config.yaml"):
    """将 PipelineConfig 写回 config.yaml。"""
    # Phase 2.1: 保存时失效缓存，下次 load_config 重新解析
    _config_cache.pop(os.path.abspath(config_path), None)
    data = _config_to_dict(cfg)
    existing = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            existing = {}
    for obsolete in ("runninghub", "audio", "storyboard", "web_video", "workflow_ids"):
        existing.pop(obsolete, None)
    data = _deep_merge(existing, data)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info(f"配置已保存: {config_path}")


def save_api_keys(
    llm_key: str,
    yunying_key: str,
    env_path: Optional[str] = None,
) -> str:
    """Persist settings-managed API keys to the highest-priority .env file."""
    from core.paths import get_env_path

    target = os.path.abspath(env_path or get_env_path())
    values = {
        "LLM_API_KEY": str(llm_key or "").strip(),
        "YUNYING_API_KEY": str(yunying_key or "").strip(),
    }
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("API Key 不能包含换行符")

    lines: List[str] = []
    if os.path.isfile(target):
        with open(target, "r", encoding="utf-8-sig") as handle:
            lines = handle.read().splitlines()

    key_pattern = re.compile(
        r"^\s*(LLM_API_KEY|YUNYING_API_KEY)\s*="
    )
    updated: List[str] = []
    seen = set()
    for line in lines:
        match = key_pattern.match(line)
        if not match:
            updated.append(line)
            continue
        key = match.group(1)
        if key not in seen:
            updated.append(f"{key}={values[key]}")
            seen.add(key)

    for key, value in values.items():
        if key not in seen:
            updated.append(f"{key}={value}")

    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(updated).rstrip("\n") + "\n")
    os.replace(temporary, target)

    for key, value in values.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    logger.info("API 密钥已同步到用户 .env")
    return target


def save_filter_options(options: Dict[str, bool], config_path: str = "config.yaml"):
    """Persist only filtering options without resolving or rewriting path values."""
    data = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    current = data.setdefault("filter_options", {})
    current.update({key: bool(value) for key, value in options.items()})
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info(f"过滤配置已保存: {config_path}")


def _deep_merge(base: dict, updates: dict) -> dict:
    result = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def save_prompt_template(path: str, sections: dict):
    """
    保存提示词模板文件。

    sections 示例:
        {"SYSTEM": "你是...", "USER": "以下是...{screenplay_text}...", "SCHEMA": "delimiter: ..."}
    写回格式: ---SYSTEM---\n...\n---USER---\n...\n---SCHEMA---\n...
    """
    parts = []
    for key in ("SYSTEM", "USER", "SCHEMA"):
        if key in sections and sections[key].strip():
            parts.append(f"---{key}---\n{sections[key].strip()}")
    content = "\n".join(parts) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"提示词模板已保存: {path}")


def load_prompt_template(path: str) -> dict:
    """读取提示词模板文件，返回 {"SYSTEM": "...", "USER": "...", "SCHEMA": "..."}"""
    sections = {}
    if not os.path.exists(path):
        return sections
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    import re
    parts = re.split(r"^---(\w+)---\s*$", text, flags=re.MULTILINE)
    # parts[0] is before first ---KEY--- (usually empty)
    # then alternating: KEY, content, KEY, content...
    i = 1
    while i + 1 < len(parts):
        sections[parts[i]] = parts[i + 1].strip()
        i += 2
    return sections


class ConfigError:
    """配置校验错误条目"""
    def __init__(self, field: str, message: str, hint: str = ""):
        self.field: str = field
        self.message: str = message
        self.hint: str = hint

    def __str__(self) -> str:
        s = f"  ✗ {self.field}: {self.message}"
        if self.hint:
            s += f"\n    → {self.hint}"
        return s


def _validate_config(cfg: PipelineConfig, env_path: str = ".env") -> Tuple[List[ConfigError], List[ConfigError]]:
    """
    校验配置项健全性，记录警告但不阻断。

    在 load_config() 末尾调用，检查所有必填项和常见错误配置，
    给出明确提示而非让程序在运行中崩溃。
    """
    errors: List[ConfigError] = []
    warnings: List[ConfigError] = []

    # ===== 必填项: API Keys =====
    if not cfg.media.api_key:
        errors.append(ConfigError(
            "YUNYING_API_KEY",
            "云映媒体 API Key 未配置",
            f"请在 {env_path} 中设置 YUNYING_API_KEY=你的密钥",
        ))

    if not cfg.llm.api_key:
        errors.append(ConfigError(
            "LLM_API_KEY",
            "LLM API Key 未配置",
            f"请在 {env_path} 中设置 LLM_API_KEY=你的密钥 "
            f"(支持: 火山引擎Ark / DeepSeek / OpenAI)",
        ))

    # ===== 可选项: 检查明显错误 =====

    # API Key 格式检查 (占位符)
    placeholder_values = {"your_", "你的", "xxx", "YOUR_", "填入", "placeholder"}
    if cfg.media.api_key:
        if any(cfg.media.api_key.lower().startswith(p) for p in placeholder_values):
            warnings.append(ConfigError(
                "YUNYING_API_KEY",
                "看起来是占位符，请替换为真实密钥",
            ))

    if cfg.llm.api_key:
        if any(cfg.llm.api_key.lower().startswith(p) for p in placeholder_values):
            warnings.append(ConfigError(
                "LLM_API_KEY",
                "看起来是占位符，请替换为真实密钥",
            ))

    # base_url 格式
    if cfg.media.base_url and not cfg.media.base_url.startswith("http"):
        warnings.append(ConfigError(
            "media.base_url",
            f"URL 格式异常: {cfg.media.base_url}",
            "应以 https:// 开头",
        ))

    if cfg.llm.base_url and not cfg.llm.base_url.startswith("http"):
        warnings.append(ConfigError(
            "llm.base_url",
            f"URL 格式异常: {cfg.llm.base_url}",
            "应以 https:// 开头",
        ))

    # 超时时间合理性
    if cfg.media.timeout < 60:
        warnings.append(ConfigError(
            "media.timeout",
            f"超时时间过短 ({cfg.media.timeout}s)，视频任务可能需要较长时间",
            "建议至少设为 600",
        ))

    # 提示词模板文件存在性
    if cfg.prompt_template_path and not os.path.exists(cfg.prompt_template_path):
        warnings.append(ConfigError(
            "prompt.template_path",
            f"提示词模板文件不存在: {cfg.prompt_template_path}",
            "将使用内置默认提示词",
        ))

    if cfg.asset_template_path and not os.path.exists(cfg.asset_template_path):
        warnings.append(ConfigError(
            "asset.template_path",
            f"资产提示词模板不存在: {cfg.asset_template_path}",
            "将使用内置默认提示词",
        ))

    # ===== 输出结果 =====
    if errors:
        logger.error(f"配置校验发现 {len(errors)} 个错误:")
        for err in errors:
            logger.error(str(err))

    if warnings:
        logger.warning(f"配置校验发现 {len(warnings)} 个警告:")
        for warn in warnings:
            logger.warning(str(warn))

    return errors, warnings


def _merge_yaml(cfg: PipelineConfig, raw: Dict[str, Any]) -> None:
    """将 YAML 字典合并到 PipelineConfig"""

    media = raw.get("media", {})
    for key in ("api_key", "base_url", "video_model", "image_model",
                "timeout", "poll_interval", "request_timeout"):
        if key in media:
            setattr(cfg.media, key, media[key])

    # LLM
    llm = raw.get("llm", {})
    for key in ("api_key", "base_url", "model", "max_tokens",
                "context_window", "temperature", "timeout", "use_cache", "cache_path"):
        if key in llm:
            setattr(cfg.llm, key, llm[key])

    # Asset
    asset_cfg = raw.get("asset", {})
    for key in ("max_input_chars", "prompt_node_id",
                "character_template_path", "scene_template_path",
                "prop_template_path", "selector_template_path"):
        if key in asset_cfg:
            setattr(cfg.asset, key, asset_cfg[key])

    # Filter options
    fo = raw.get("filter_options", {})
    for key in (
        "filter_episode_title", "filter_colon_title",
        "filter_version", "filter_next_episode",
        "filter_word_heading", "filter_large_font",
        "filter_short_bold", "filter_bracket_title",
        "filter_table_content",
    ):
        if key in fo:
            setattr(cfg.filter_options, key, fo[key])

    # Top-level fields
    project = raw.get("project", {})
    if "root" in project:
        cfg.project_root = project["root"]

    prompt = raw.get("prompt", {})
    if "template_path" in prompt:
        cfg.prompt_template_path = prompt["template_path"]

    asset = raw.get("asset", {})
    if "template_path" in asset:
        cfg.asset_template_path = asset["template_path"]

    # Max episodes
    pipeline_cfg = raw.get("pipeline", {})
    if "max_episodes" in pipeline_cfg:
        cfg.max_episodes = pipeline_cfg["max_episodes"]

    # External tools
    tools = raw.get("tools", {})
    if "ffmpeg_path" in tools:
        cfg.ffmpeg_path = tools["ffmpeg_path"]
    if "jianying_path" in tools:
        cfg.jianying_path = tools["jianying_path"]

    # Prompt Templates
    prompt_templates = raw.get("prompt_templates", {})
    if prompt_templates:
        cfg.prompt_templates.update(prompt_templates)

    log_cfg = raw.get("logging", {})
    if "level" in log_cfg:
        cfg.log_level = log_cfg["level"]


def _apply_env_overrides(cfg: PipelineConfig) -> None:
    """从环境变量覆盖配置"""

    def usable(value: Optional[str]) -> bool:
        normalized = str(value or "").strip().lower()
        return bool(normalized) and not normalized.startswith((
            "your_", "your-", "placeholder", "xxx", "填入", "你的", "<your",
        ))

    env_media_key = os.getenv("YUNYING_API_KEY")
    if usable(env_media_key):
        cfg.media.api_key = str(env_media_key)
    env_media_url = os.getenv("YUNYING_BASE_URL")
    if env_media_url:
        cfg.media.base_url = env_media_url
    env_video_model = os.getenv("YUNYING_VIDEO_MODEL")
    if env_video_model:
        cfg.media.video_model = env_video_model
    env_image_model = os.getenv("YUNYING_IMAGE_MODEL")
    if env_image_model:
        cfg.media.image_model = env_image_model

    # LLM
    env_llm_key: Optional[str] = os.getenv("LLM_API_KEY")
    if usable(env_llm_key):
        cfg.llm.api_key = env_llm_key

    env_llm_url: Optional[str] = os.getenv("LLM_BASE_URL")
    if env_llm_url:
        cfg.llm.base_url = env_llm_url

    env_llm_model: Optional[str] = os.getenv("LLM_MODEL")
    if env_llm_model:
        cfg.llm.model = env_llm_model

    env_llm_use_cache: Optional[str] = os.getenv("LLM_USE_CACHE")
    if env_llm_use_cache:
        cfg.llm.use_cache = env_llm_use_cache.lower() in ("true", "1", "yes")

    env_llm_cache_path: Optional[str] = os.getenv("LLM_CACHE_PATH")
    if env_llm_cache_path:
        cfg.llm.cache_path = env_llm_cache_path

    # Project Root
    env_project_root: Optional[str] = os.getenv("PROJECT_ROOT")
    if env_project_root:
        cfg.project_root = env_project_root

    # External tool paths
    env_ffmpeg: Optional[str] = os.getenv("FFMPEG_PATH")
    if env_ffmpeg:
        cfg.ffmpeg_path = env_ffmpeg

    env_jianying: Optional[str] = os.getenv("JIANYING_PATH")
    if env_jianying:
        cfg.jianying_path = env_jianying

def _resolve_paths(cfg: PipelineConfig, base: str) -> None:
    """将配置中的相对路径解析为绝对路径"""
    if cfg.ffmpeg_path and not os.path.isabs(cfg.ffmpeg_path):
        cfg.ffmpeg_path = os.path.normpath(os.path.join(base, cfg.ffmpeg_path))

    # project_root 使用 get_data_dir() 确保 projects/ 在 exe 旁（PyInstaller 兼容）
    from core.paths import get_data_dir
    if cfg.project_root and not os.path.isabs(cfg.project_root):
        cfg.project_root = os.path.normpath(
            os.path.join(get_data_dir(), cfg.project_root)
        )

    if cfg.prompt_template_path and not os.path.isabs(cfg.prompt_template_path):
        cfg.prompt_template_path = os.path.normpath(os.path.join(base, cfg.prompt_template_path))

    if cfg.asset_template_path and not os.path.isabs(cfg.asset_template_path):
        cfg.asset_template_path = os.path.normpath(os.path.join(base, cfg.asset_template_path))

    for _path_attr in ("character_template_path", "scene_template_path",
                       "prop_template_path", "selector_template_path"):
        _val = getattr(cfg.asset, _path_attr, "")
        if _val and not os.path.isabs(_val):
            setattr(cfg.asset, _path_attr,
                    os.path.normpath(os.path.join(base, _val)))



def setup_logging(level: str = "INFO", log_file: str = "") -> None:
    """配置全局日志"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    handlers = [logging.StreamHandler()]
    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        handlers.append(fh)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    # 降低第三方库日志
    for lib in ("httpx", "openai", "urllib3", "requests", "httpcore"):
        logging.getLogger(lib).setLevel(logging.WARNING)
