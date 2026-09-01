"""集视频接口：列表、上传。"""
import io
import os

from core.ffmpeg_runner import FFmpegRunner


def _create(client, make_script, tmp_path, monkeypatch, name="P"):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(1)
    with open(script, "rb") as handle:
        client.post("/api/projects", data={"name": name, "script": (handle, "s.txt")},
                    content_type="multipart/form-data")
    web_video = os.path.join(str(tmp_path), name, "web_video", "01")
    os.makedirs(web_video, exist_ok=True)
    FFmpegRunner().run([
        "-f", "lavfi", "-i", "color=c=red:s=160x90:r=15:d=1",
        "-pix_fmt", "yuv420p", "-y", os.path.join(web_video, "001.mp4"),
    ])


def test_list_episode_videos(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    payload = client.get("/api/projects/P/episodes/01/videos").get_json()
    assert payload["videos"] == ["web_video/01/001.mp4"]


def test_upload_episode_video(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    data = {"file": (io.BytesIO(b"\x00" * 64), "replaced.mp4")}
    response = client.post("/api/projects/P/episodes/01/videos",
                           data=data, content_type="multipart/form-data")
    assert response.status_code == 201
    relative = response.get_json()["video_path"]
    assert relative.startswith("web_video/01/")
    assert os.path.isfile(os.path.join(str(tmp_path), "P", relative))


def test_upload_rejects_bad_extension(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    data = {"file": (io.BytesIO(b"x" * 16), "evil.exe")}
    response = client.post("/api/projects/P/episodes/01/videos",
                           data=data, content_type="multipart/form-data")
    assert response.status_code == 400
