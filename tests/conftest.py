"""Shared fixtures for the Web API tests."""

import pytest


@pytest.fixture
def client():
    # 每个测试用独立的 TaskQueue，避免模块级单例跨测试污染
    from web_api import tasks as tasks_module
    from web_api.task_queue import TaskQueue

    original_queue = tasks_module.queue
    tasks_module.queue = TaskQueue(max_workers=2)
    try:
        from web_api.app import create_app

        app = create_app()
        app.config["TESTING"] = True
        yield app.test_client()
    finally:
        tasks_module.queue = original_queue


@pytest.fixture
def make_script(tmp_path):
    """Create a temporary screenplay containing the requested episode count."""

    def _make(episodes=2):
        parts = []
        for number in range(1, episodes + 1):
            parts.append(f"第{number}集\n{number}号主角登场，剧情推进。\n")
        path = tmp_path / "script.txt"
        path.write_text("\n".join(parts), encoding="utf-8")
        return str(path)

    return _make
