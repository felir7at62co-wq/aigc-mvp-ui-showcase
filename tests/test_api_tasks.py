"""任务 API：提交/查询/列表/取消。"""
import os
import time


def _create(client, make_script, tmp_path, monkeypatch, name="P"):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(2)
    with open(script, "rb") as handle:
        return client.post("/api/projects", data={"name": name, "script": (handle, "s.txt")},
                           content_type="multipart/form-data")


def test_submit_and_poll_shot_match(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    # 先造一个 prompt 产物，让 shot_match 可直接运行
    prompts = os.path.join(str(tmp_path), "P", "prompts")
    os.makedirs(prompts, exist_ok=True)
    with open(os.path.join(prompts, "01.txt"), "w", encoding="utf-8") as handle:
        handle.write("镜头 1：主角登场\n出镜人物【主角】\n核心场景：办公室\n")
    response = client.post("/api/projects/P/tasks", json={
        "step": "shot_match", "episodes": ["01"],
    })
    assert response.status_code == 202
    task_id = response.get_json()["task_id"]
    deadline = time.time() + 20
    status = "queued"
    payload = {}
    while time.time() < deadline:
        payload = client.get(f"/api/projects/P/tasks/{task_id}").get_json()
        status = payload["status"]
        if status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert status == "completed", payload
    matches = os.path.join(str(tmp_path), "P", "matches", "01.json")
    assert os.path.isfile(matches)


def test_submit_rejects_unknown_step(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    response = client.post("/api/projects/P/tasks", json={"step": "nope", "episodes": ["01"]})
    assert response.status_code == 400


def test_list_tasks(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    client.post("/api/projects/P/tasks", json={"step": "shot_match", "episodes": ["01"]})
    payload = client.get("/api/projects/P/tasks").get_json()
    assert any(item["step"] == "shot_match" for item in payload["tasks"])


def test_cancel_task(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    response = client.post("/api/projects/P/tasks", json={"step": "shot_match", "episodes": ["01"]})
    task_id = response.get_json()["task_id"]
    response = client.post(f"/api/projects/P/tasks/{task_id}/cancel")
    assert response.status_code == 200
    assert client.get(f"/api/projects/P/tasks/{task_id}").get_json()["status"] in (
        "cancelled", "completed", "failed",
    )
