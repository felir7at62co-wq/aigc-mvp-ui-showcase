"""预览与导出 API + /media 静态服务。"""
import os
import time

from core.ffmpeg_runner import FFmpegRunner


def _create(client, make_script, tmp_path, monkeypatch, name="P"):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(1)
    with open(script, "rb") as handle:
        client.post("/api/projects", data={"name": name, "script": (handle, "s.txt")},
                    content_type="multipart/form-data")
    # 造一个视频 + 时间线
    web_video = os.path.join(str(tmp_path), name, "web_video", "01")
    os.makedirs(web_video, exist_ok=True)
    FFmpegRunner().run([
        "-f", "lavfi", "-i", "color=c=red:s=160x90:r=15:d=1",
        "-pix_fmt", "yuv420p", "-y", os.path.join(web_video, "001.mp4"),
    ])
    client.put(f"/api/projects/{name}/timeline/01", json={"create_if_missing": True})


def _wait_task(client, project, task_id, timeout=40):
    deadline = time.time() + timeout
    record = {}
    while time.time() < deadline:
        record = client.get(f"/api/projects/{project}/tasks/{task_id}").get_json()
        if record["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.2)
    return record


def test_trigger_preview_and_fetch_video(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    response = client.post("/api/projects/P/preview/01", json={})
    assert response.status_code == 202
    task_id = response.get_json()["task_id"]
    record = _wait_task(client, "P", task_id)
    assert record["status"] == "completed", record
    preview = client.get("/api/projects/P/preview/01").get_json()
    assert preview["status"] == "completed"
    assert preview["preview_path"].startswith("exports/")
    video = client.get(f"/api/projects/P/media/{preview['preview_path']}")
    assert video.status_code == 200
    assert video.content_type.startswith("video/")


def test_trigger_export(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    response = client.post("/api/projects/P/exports", json={"episodes": ["01"], "prefix": "T_"})
    assert response.status_code == 202
    task_id = response.get_json()["task_id"]
    record = _wait_task(client, "P", task_id)
    # 无剪映模板环境允许 failed；只要求任务结束且状态可查
    assert record["status"] in ("completed", "failed"), record
    exports = client.get("/api/projects/P/exports").get_json()
    assert exports["episodes"]["01"]["status"] in ("completed", "failed", "pending")


def test_media_serves_asset_image(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    assets = os.path.join(str(tmp_path), "P", "assets", "character")
    os.makedirs(assets, exist_ok=True)
    with open(os.path.join(assets, "主角.png"), "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    response = client.get("/api/projects/P/media/assets/character/主角.png")
    assert response.status_code == 200
    assert response.content_type == "image/png"


def test_media_rejects_path_traversal(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    response = client.get("/api/projects/P/media/../../config.yaml")
    assert response.status_code == 404
