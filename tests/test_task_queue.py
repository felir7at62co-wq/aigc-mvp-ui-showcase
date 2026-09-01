"""任务队列：StepRunner 契约 + 线程池执行 + 状态记录。"""
import time

from core.project import Project
from web_api.task_queue import TaskQueue


def _make_project(tmp_path) -> Project:
    """创建一个真实的最小项目（TaskQueue._run 需要 Project.load 成功）。"""
    root = tmp_path / "projects"
    script = tmp_path / "script.txt"
    script.write_text("第1集\n主角登场。\n第2集\n剧情推进。\n", encoding="utf-8")
    return Project.create(str(root), "demo", str(script))


def test_submit_runs_operation_and_records_result(tmp_path):
    queue = TaskQueue(max_workers=2)
    project = _make_project(tmp_path)
    calls = []

    def fake_operation(project_arg, episode_id, options, cancelled):
        calls.append(episode_id)
        return {"success": True, "status": "completed", "output_path": f"out/{episode_id}.txt"}

    task_id = queue.submit(project.project_dir, "prompt", ["01", "02"], {}, fake_operation)
    deadline = time.time() + 15
    while time.time() < deadline and queue.get(task_id).status != "completed":
        time.sleep(0.05)
    record = queue.get(task_id)
    assert record.status == "completed"
    assert sorted(calls) == ["01", "02"]
    assert record.results == {"01": "out/01.txt", "02": "out/02.txt"}


def test_list_and_get(tmp_path):
    queue = TaskQueue(max_workers=2)
    project = _make_project(tmp_path)
    task_id = queue.submit(
        project.project_dir, "shot_match", ["01"], {},
        lambda *args, **kwargs: {"success": True},
    )
    assert task_id in [item["id"] for item in queue.list()]


def test_cancel_running_task(tmp_path):
    queue = TaskQueue(max_workers=1)
    project = _make_project(tmp_path)

    def slow(project_arg, episode_id, options, cancelled):
        for _ in range(50):
            if cancelled.is_set():
                return {"success": False, "status": "cancelled"}
            time.sleep(0.02)
        return {"success": True}

    task_id = queue.submit(project.project_dir, "video", ["01"], {}, slow)
    time.sleep(0.1)  # 确保任务已进入 running
    queue.cancel(task_id)
    deadline = time.time() + 15
    while time.time() < deadline and queue.get(task_id).status == "running":
        time.sleep(0.05)
    assert queue.get(task_id).status == "cancelled"


def test_operation_failure_records_failed(tmp_path):
    queue = TaskQueue(max_workers=1)
    project = _make_project(tmp_path)

    def failing(project_arg, episode_id, options, cancelled):
        return {"success": False, "error": "模拟失败"}

    task_id = queue.submit(project.project_dir, "prompt", ["01"], {}, failing)
    deadline = time.time() + 15
    while time.time() < deadline and queue.get(task_id).status in ("queued", "running"):
        time.sleep(0.05)
    record = queue.get(task_id)
    assert record.status == "failed"
    assert "模拟失败" in record.failures.get("01", "")
