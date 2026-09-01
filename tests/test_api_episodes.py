def _create(client, make_script, tmp_path, monkeypatch, name="P"):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(2)
    with open(script, "rb") as handle:
        return client.post(
            "/api/projects",
            data={"name": name, "script": (handle, "s.txt")},
            content_type="multipart/form-data",
        )


def test_episode_list(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)

    response = client.get("/api/projects/P/episodes")

    assert response.status_code == 200
    episodes = response.get_json()["episodes"]
    assert [item["episode_id"] for item in episodes] == ["01", "02"]
    assert all("shot_match_status" in item for item in episodes)


def test_episode_detail(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)

    response = client.get("/api/projects/P/episodes/01")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["episode_id"] == "01"
    assert "1号主角登场" in payload["text"]
    assert payload["artifacts"]["shot_match"]["status"] == "pending"


def test_episode_detail_missing(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)

    assert client.get("/api/projects/P/episodes/99").status_code == 404
