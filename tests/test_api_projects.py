import os

from core.project_settings import DEFAULT_PROJECT_SETTINGS, load_project_settings


def test_create_project_splits_episodes(client, make_script, monkeypatch, tmp_path):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(episodes=3)
    with open(script, "rb") as handle:
        response = client.post(
            "/api/projects",
            data={"name": "测试项目", "script": (handle, "script.txt")},
            content_type="multipart/form-data",
        )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["name"] == "测试项目"
    assert payload["episode_count"] == 3
    assert payload["steps"]["import_script"]["status"] == "completed"
    project_dir = os.path.join(str(tmp_path), "测试项目")
    episodes = os.listdir(os.path.join(project_dir, "analysis", "episodes"))
    assert sorted(episodes) == ["01.txt", "02.txt", "03.txt"]
    for step in ("prompt", "asset", "shot_match", "video", "timeline", "preview", "export"):
        assert payload["steps"][step]["status"] == "pending"


def test_create_project_saves_hidden_defaults_and_visible_video_preferences(
    client, make_script, monkeypatch, tmp_path
):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(episodes=2)
    with open(script, "rb") as handle:
        response = client.post(
            "/api/projects",
            data={
                "name": "配置项目",
                "script": (handle, "配置项目.txt"),
                "aspect_ratio": "16:9",
                "resolution": "1080p",
                "prompt_prefix": "电影感，角色一致",
            },
            content_type="multipart/form-data",
        )

    assert response.status_code == 201
    settings = load_project_settings(os.path.join(str(tmp_path), "配置项目"))
    assert settings == {
        **DEFAULT_PROJECT_SETTINGS,
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "prompt_prefix": "电影感，角色一致",
    }


def test_project_settings_endpoint_gets_and_updates_safe_fields(
    client, make_script, monkeypatch, tmp_path
):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(1)
    with open(script, "rb") as handle:
        client.post(
            "/api/projects",
            data={"name": "设置项目", "script": (handle, "s.txt")},
            content_type="multipart/form-data",
        )

    initial = client.get("/api/projects/设置项目/settings")
    assert initial.status_code == 200
    assert initial.get_json()["resolution"] == "720p"
    assert "api_key" not in initial.get_json()

    updated = client.put(
        "/api/projects/设置项目/settings",
        json={
            "aspect_ratio": "4:3",
            "resolution": "1080p",
            "prompt_prefix": "纪实光线",
            "video_model": "malicious-override",
            "batch_duration": 4,
        },
    )
    assert updated.status_code == 200
    payload = updated.get_json()
    assert payload["aspect_ratio"] == "4:3"
    assert payload["resolution"] == "1080p"
    assert payload["prompt_prefix"] == "纪实光线"
    assert payload["video_model"] == "seedance-2-0-official"
    assert payload["batch_duration"] == 15


def test_create_project_requires_script(client):
    response = client.post(
        "/api/projects", data={"name": "无剧本"}, content_type="multipart/form-data"
    )

    assert response.status_code == 400


def test_list_projects_empty_and_after_create(client, make_script, monkeypatch, tmp_path):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    assert client.get("/api/projects").get_json() == {"projects": []}
    script = make_script(1)
    with open(script, "rb") as handle:
        client.post(
            "/api/projects",
            data={"name": "A", "script": (handle, "s.txt")},
            content_type="multipart/form-data",
        )

    payload = client.get("/api/projects").get_json()
    assert [item["name"] for item in payload["projects"]] == ["A"]


def test_get_project_summary_shape(client, make_script, monkeypatch, tmp_path):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(2)
    with open(script, "rb") as handle:
        client.post(
            "/api/projects",
            data={"name": "B", "script": (handle, "s.txt")},
            content_type="multipart/form-data",
        )

    payload = client.get("/api/projects/B").get_json()
    assert payload["name"] == "B"
    assert payload["episodes"]["total"] == 2
    assert "steps" in payload
    assert "created_at" in payload


def test_delete_project(client, make_script, monkeypatch, tmp_path):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(1)
    with open(script, "rb") as handle:
        client.post(
            "/api/projects",
            data={"name": "C", "script": (handle, "s.txt")},
            content_type="multipart/form-data",
        )

    assert client.delete("/api/projects/C").status_code == 200
    assert client.get("/api/projects/C").status_code == 404


def test_get_missing_project_404(client):
    assert client.get("/api/projects/不存在").status_code == 404
