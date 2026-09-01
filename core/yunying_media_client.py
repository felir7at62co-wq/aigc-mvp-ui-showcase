"""Yunying OpenAI-compatible image and video generation client."""

from __future__ import annotations

import base64
import os
import tempfile
import threading
import time
from typing import Any, Mapping, Optional

import requests


class YunyingMediaClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://wy6688.token6688.com/v1",
        video_model: str = "seedance-2-0-official",
        image_model: str = "gpt-image-2-official",
        timeout: int = 4500,
        poll_interval: float = 5,
        request_timeout: int = 120,
    ) -> None:
        if not str(api_key).strip():
            raise RuntimeError("YUNYING_API_KEY 未配置")
        if os.environ.get("AIGC_DISABLE_NETWORK"):
            raise RuntimeError("AIGC_DISABLE_NETWORK 已设置，禁止初始化云映媒体客户端")
        self._api_key = str(api_key).strip()
        self.base_url = str(base_url).rstrip("/")
        self.video_model = video_model
        self.image_model = image_model
        self.timeout = int(timeout)
        self.poll_interval = float(poll_interval)
        self.request_timeout = int(request_timeout)
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self._api_key}"})

    def __repr__(self) -> str:
        return (
            f"YunyingMediaClient(base_url={self.base_url!r}, "
            f"video_model={self.video_model!r}, image_model={self.image_model!r})"
        )

    @classmethod
    def from_env(cls, **overrides: Any) -> "YunyingMediaClient":
        values = {
            "api_key": os.getenv("YUNYING_API_KEY", ""),
            "base_url": os.getenv("YUNYING_BASE_URL", "https://wy6688.token6688.com/v1"),
            "video_model": os.getenv("YUNYING_VIDEO_MODEL", "seedance-2-0-official"),
            "image_model": os.getenv("YUNYING_IMAGE_MODEL", "gpt-image-2-official"),
        }
        values.update(overrides)
        return cls(**values)

    def upload_file(self, file_path: str) -> str:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(file_path)
        with open(file_path, "rb") as handle:
            response = self.session.post(
                f"{self.base_url}/files",
                files={"file": (os.path.basename(file_path), handle)},
                timeout=self.request_timeout,
            )
        response.raise_for_status()
        payload = response.json()
        url = self._first_text(payload, "url", "file_url", "download_url")
        if not url and isinstance(payload.get("data"), Mapping):
            url = self._first_text(payload["data"], "url", "file_url", "download_url")
        if not url:
            raise RuntimeError("文件上传成功，但响应中缺少 URL")
        return url

    def generate_image(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        aspect_ratio: str = "1:1",
        resolution: str = "2k",
        quality: str = "high",
    ) -> dict[str, Any]:
        selected_model = model or self.image_model
        payload: dict[str, Any] = {
            "model": selected_model,
            "prompt": prompt,
            "resolution": resolution.lower(),
            "quality": quality,
        }
        if selected_model.endswith("-official"):
            payload["size"] = aspect_ratio
        else:
            payload["aspect_ratio"] = aspect_ratio
            payload["resolution"] = resolution.upper()
        response = self.session.post(
            f"{self.base_url}/images/generations",
            json=payload,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        result = response.json()
        items = result.get("data") if isinstance(result, Mapping) else None
        item = items[0] if isinstance(items, list) and items else result
        if isinstance(item, Mapping) and item.get("url"):
            return {"url": str(item["url"])}
        if isinstance(item, Mapping) and item.get("b64_json"):
            return {"bytes": base64.b64decode(str(item["b64_json"]))}
        raise RuntimeError("图片生成成功，但响应中缺少 url 或 b64_json")

    def create_video_task(
        self,
        *,
        prompt: str,
        images: list[str],
        duration: int = 15,
        resolution: str = "720p",
        aspect_ratio: str = "9:16",
        mode: str = "reference",
        model: Optional[str] = None,
    ) -> str:
        payload = {
            "model": model or self.video_model,
            "prompt": prompt,
            "duration": int(duration),
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "mode": mode,
            "images": list(images),
        }
        response = self.session.post(
            f"{self.base_url}/videos/generations",
            json=payload,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        result = response.json()
        task_id = self._first_text(result, "id", "task_id")
        if not task_id and isinstance(result.get("data"), Mapping):
            task_id = self._first_text(result["data"], "id", "task_id")
        if not task_id:
            raise RuntimeError("视频任务创建失败：响应中缺少任务 ID")
        return task_id

    def wait_for_video(
        self,
        task_id: str,
        cancel_event: Optional[threading.Event] = None,
    ) -> str:
        started = time.monotonic()
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("用户取消")
            if time.monotonic() - started > self.timeout:
                raise TimeoutError(f"视频生成任务超时 ({self.timeout}s)")
            response = self.session.get(
                f"{self.base_url}/tasks/{task_id}", timeout=self.request_timeout
            )
            response.raise_for_status()
            payload = response.json()
            status = str(payload.get("status", "")).lower()
            if status in {"failed", "error", "cancelled", "canceled", "expired"}:
                error = (
                    payload.get("error_message")
                    or payload.get("error")
                    or payload.get("message")
                    or status
                )
                if isinstance(error, Mapping):
                    error = error.get("message") or error.get("code") or "未知错误"
                raise RuntimeError(f"视频生成失败: {error}")
            is_final = bool(payload.get("is_final")) or status in {"completed", "succeeded", "success"}
            if is_final:
                url = self._extract_video_url(payload)
                if not url:
                    raise RuntimeError("视频任务已完成，但响应中缺少视频 URL")
                return url
            if cancel_event is not None:
                cancel_event.wait(self.poll_interval)
            elif self.poll_interval:
                time.sleep(self.poll_interval)

    def download(self, url: str, output_path: str) -> str:
        response = self.session.get(url, timeout=self.request_timeout, stream=True)
        response.raise_for_status()
        directory = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=directory, suffix=".part") as handle:
            temporary = handle.name
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)
        os.replace(temporary, output_path)
        return output_path

    def generate_video_and_wait(
        self,
        *,
        prompt: str,
        images: list[str],
        output_path: str,
        duration: int = 15,
        resolution: str = "720p",
        aspect_ratio: str = "9:16",
        mode: str = "reference",
        model: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> dict[str, str]:
        task_id = self.create_video_task(
            prompt=prompt,
            images=images,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            mode=mode,
            model=model,
        )
        url = self.wait_for_video(task_id, cancel_event=cancel_event)
        self.download(url, output_path)
        return {"task_id": task_id, "output_path": output_path, "url": url}

    @staticmethod
    def _first_text(payload: Mapping[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    @classmethod
    def _extract_video_url(cls, payload: Mapping[str, Any]) -> str:
        direct = cls._first_text(payload, "url", "video_url", "output_url")
        if direct:
            return direct
        for key in ("result", "output", "data"):
            nested = payload.get(key)
            if isinstance(nested, Mapping):
                found = cls._extract_video_url(nested)
                if found:
                    return found
            if isinstance(nested, list):
                for item in nested:
                    if isinstance(item, Mapping):
                        found = cls._extract_video_url(item)
                        if found:
                            return found
        return ""
