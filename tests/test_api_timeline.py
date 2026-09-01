"""时间线 API：GET 缺省 404，PUT 建初始/更新版本。"""
import os
import subprocess

from core.paths import get_ffmpeg_path


def _create(client, make_script, tmp_path, monkeypatch):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(1)
    with open(script, "rb") as handle:
        client.post("/api/projects", data={"name": "P", "script": (handle, "s.txt")},
                    content_type="multipart/form-data")


def _make_clip(web_video, name, color="red"):
    os.makedirs(web_video, exist_ok=True)
    subprocess.run([
        get_ffmpeg_path(), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=15:d=1",
        "-pix_fmt", "yuv420p", "-y", os.path.join(web_video, name),
    ], check=True)


def test_get_timeline_404_when_absent(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    assert client.get("/api/projects/P/timeline/01").status_code == 404


def test_put_create_initial_from_videos(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    _make_clip(os.path.join(str(tmp_path), "P", "web_video", "01"), "001.mp4")
    _make_clip(os.path.join(str(tmp_path), "P", "web_video", "01"), "002.mp4", "blue")
    response = client.put("/api/projects/P/timeline/01", json={
        "create_if_missing": True, "fps": 30, "width": 1080, "height": 1920,
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["episode_id"] == "01"
    assert payload["version"] == 1        # 构建 version=0，首次保存 -> 1
    assert len(payload["segments"]) == 2
    assert all(segment["trim_out"] > 0.9 for segment in payload["segments"])


def test_put_update_trims_and_bumps_version(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    _make_clip(os.path.join(str(tmp_path), "P", "web_video", "01"), "001.mp4")
    client.put("/api/projects/P/timeline/01", json={"create_if_missing": True})
    timeline = client.get("/api/projects/P/timeline/01").get_json()
    timeline["segments"][0]["trim_out"] = 0.6
    response = client.put("/api/projects/P/timeline/01", json=timeline)
    assert response.status_code == 200
    assert response.get_json()["version"] == 2
    assert response.get_json()["segments"][0]["trim_out"] == 0.6


def test_put_rejects_invalid_timeline(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    response = client.put("/api/projects/P/timeline/01", json={
        "episode_id": "01", "segments": [{
            "id": "01-001", "shot_id": "shot-001", "source_video": "x.mp4",
            "trim_in": 3.0, "trim_out": 2.0, "order": 0,
            "transition_to_next": {"type": "hard", "duration": 0.0},
        }],
    })
    assert response.status_code == 400
