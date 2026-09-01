"""Runtime checks and user-data initialization for the portable build."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from core.paths import get_app_dir, get_data_dir

APP_VERSION = "1.0.0"


def _data_path(*parts: str) -> Path:
    return Path(get_data_dir()).joinpath(*parts)


def ensure_user_data_dirs() -> None:
    """Create writable directories without overwriting existing user data."""
    for relative in ("projects", "data", "logs"):
        _data_path(*Path(relative).parts).mkdir(parents=True, exist_ok=True)

    env_path = _data_path(".env")
    example_path = Path(get_app_dir()) / ".env.example"
    if not env_path.exists() and example_path.is_file():
        shutil.copyfile(example_path, env_path)


def _required_resources() -> tuple[str, ...]:
    return (
        "config.yaml",
        ".env.example",
        "prompts/default_shot_prompt.txt",
        "prompts/default_asset_prompt.txt",
        "prompts/default_character_prompt.txt",
        "prompts/default_scene_prompt.txt",
        "prompts/default_prop_prompt.txt",
        "prompts/default_asset_selector_prompt.txt",
        "tools/ffmpeg/ffmpeg.exe",
        "tools/ffmpeg/ffprobe.exe",
    )


def validate_packaged_runtime() -> list[str]:
    """Return missing or invalid bundled resources; do not raise on startup."""
    root = Path(get_app_dir())
    errors: list[str] = []
    for relative in _required_resources():
        path = root / relative
        if not path.is_file():
            errors.append(f"缺少内置资源: {relative}")

    for executable in (root / "tools/ffmpeg/ffmpeg.exe", root / "tools/ffmpeg/ffprobe.exe"):
        if executable.is_file() and executable.stat().st_size < 1024:
            errors.append(f"内置媒体工具文件异常: {executable.relative_to(root)}")
    return errors


def _redact(value: str) -> str:
    patterns = (
        r"(?i)(api[_-]?key\s*[:=]\s*)([^\s,;]+)",
        r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s,;]+)",
        r"(?i)(sk-[A-Za-z0-9_-]{8,})",
    )
    result = value
    for pattern in patterns:
        result = re.sub(pattern, r"\1***", result)
    return result


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(str(record.msg))
        if record.args:
            record.args = tuple(_redact(str(arg)) for arg in record.args)
        return True


def configure_startup_logging() -> Path:
    ensure_user_data_dirs()
    log_path = _data_path("logs", "startup.log")
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return log_path


def report_startup_failure(message: str) -> None:
    """Write a safe diagnostic and show a native Windows message when possible."""
    safe_message = _redact(message)
    try:
        log_path = _data_path("logs", "startup.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat()} [ERROR] {safe_message}\n")
    except OSError:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, safe_message, "AIGC Pipeline 启动失败", 0x10)
        except Exception:
            pass


def _iter_manifest_files(root: Path) -> Iterable[Path]:
    ignored = {".env", "build-manifest.json"}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in ignored:
            yield path


def create_release_manifest(output_dir: str) -> dict:
    """Create a reproducible resource inventory for a completed release."""
    root = Path(output_dir)
    files = []
    for path in _iter_manifest_files(root):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"path": str(path.relative_to(root)), "sha256": digest, "size": path.stat().st_size})
    manifest = {
        "application": "AIGC Pipeline",
        "version": APP_VERSION,
        "platform": "windows-x64",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    (root / "build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
