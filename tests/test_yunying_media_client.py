import base64
import os

import pytest

from core.yunying_media_client import YunyingMediaClient


class FakeResponse:
    def __init__(self, payload=None, content=b"", chunks=None):
        self.payload = payload or {}
        self.content = content
        self._chunks = chunks or ([content] if content else [])

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload

    def iter_content(self, chunk_size=8192):
        return iter(self._chunks)


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []
        self.post_responses = []
        self.get_responses = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.post_responses.pop(0)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.get_responses.pop(0)


def make_client():
    client = YunyingMediaClient(
        api_key="test-key",
        base_url="https://media.example/v1/",
        poll_interval=0,
    )
    client.session = FakeSession()
    client.session.headers.update({"Authorization": "Bearer test-key"})
    return client


def test_upload_file_posts_multipart_and_returns_url(tmp_path):
    image = tmp_path / "ref.png"
    image.write_bytes(b"png")
    client = make_client()
    client.session.post_responses.append(FakeResponse({"url": "https://cdn/ref.png"}))

    assert client.upload_file(str(image)) == "https://cdn/ref.png"
    method, url, kwargs = client.session.calls[0]
    assert (method, url) == ("POST", "https://media.example/v1/files")
    assert "file" in kwargs["files"]


def test_generate_image_uses_official_model_contract():
    client = make_client()
    client.session.post_responses.append(FakeResponse({"data": [{"url": "https://cdn/image.png"}]}))

    result = client.generate_image(
        "角色设定图", aspect_ratio="9:16", resolution="2k"
    )

    assert result == {"url": "https://cdn/image.png"}
    _, url, kwargs = client.session.calls[0]
    assert url == "https://media.example/v1/images/generations"
    assert kwargs["json"] == {
        "model": "gpt-image-2-official",
        "prompt": "角色设定图",
        "size": "9:16",
        "resolution": "2k",
        "quality": "high",
    }


def test_generate_image_supports_base64_output():
    client = make_client()
    encoded = base64.b64encode(b"image-data").decode("ascii")
    client.session.post_responses.append(FakeResponse({"data": [{"b64_json": encoded}]}))
    assert client.generate_image("场景")["bytes"] == b"image-data"


def test_video_generation_polls_final_task_and_downloads(tmp_path):
    client = make_client()
    client.session.post_responses.append(FakeResponse({"id": "task-1"}))
    client.session.get_responses.extend([
        FakeResponse({"id": "task-1", "status": "processing", "is_final": False}),
        FakeResponse({"id": "task-1", "status": "completed", "is_final": True, "result": {"url": "https://cdn/video.mp4"}}),
        FakeResponse(content=b"video", chunks=[b"vi", b"deo"]),
    ])
    output = tmp_path / "batch.mp4"

    result = client.generate_video_and_wait(
        prompt="完整镜头脚本",
        images=["https://cdn/a.png"],
        output_path=str(output),
        duration=15,
        resolution="720p",
        aspect_ratio="9:16",
    )

    assert result["task_id"] == "task-1"
    assert output.read_bytes() == b"video"
    _, url, kwargs = client.session.calls[0]
    assert url == "https://media.example/v1/videos/generations"
    assert kwargs["json"] == {
        "model": "seedance-2-0-official",
        "prompt": "完整镜头脚本",
        "duration": 15,
        "resolution": "720p",
        "aspect_ratio": "9:16",
        "mode": "reference",
        "images": ["https://cdn/a.png"],
    }
    assert client.session.calls[1][1] == "https://media.example/v1/tasks/task-1"


def test_from_env_requires_key_without_echoing_secret(monkeypatch):
    monkeypatch.delenv("YUNYING_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="YUNYING_API_KEY") as error:
        YunyingMediaClient.from_env()
    assert "test-key" not in str(error.value)


def test_client_repr_does_not_expose_key():
    client = make_client()
    assert "test-key" not in repr(client)


def test_video_failure_uses_documented_error_message():
    client = make_client()
    client.session.get_responses.append(FakeResponse({
        "status": "failed",
        "is_final": True,
        "error_message": "reference image exceeds model limit",
    }))

    with pytest.raises(RuntimeError, match="reference image exceeds model limit"):
        client.wait_for_video("task-failed")
