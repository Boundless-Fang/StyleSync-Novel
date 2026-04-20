import sys
from pathlib import Path

from fastapi.testclient import TestClient


CODE_DIR = Path(__file__).resolve().parents[1] / "style_imitation_code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from main import app  # noqa: E402
from api import routeworkflow  # noqa: E402


client = TestClient(app)


async def _noop_async(*args, **kwargs):
    return None


def _prepare_fake_script_dir(tmp_path, script_name: str) -> Path:
    code_dir = tmp_path / "code"
    scripts_dir = code_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / script_name).write_text("# fake script\n", encoding="utf-8")
    return code_dir


def test_cancel_latest_task_returns_noop(monkeypatch):
    async def fake_cancel_latest():
        return None

    monkeypatch.setattr(routeworkflow, "cancel_latest_task", fake_cancel_latest)

    response = client.post("/api/task-actions/cancel_latest")

    assert response.status_code == 200
    assert response.json()["status"] == "noop"


def test_cancel_all_tasks_returns_summary(monkeypatch):
    async def fake_cancel_all():
        return [
            {"task_id": "task-1", "task_name": "f5a demo"},
            {"task_id": "task-2", "task_name": "f5b demo"},
        ]

    monkeypatch.setattr(routeworkflow, "cancel_all_tasks", fake_cancel_all)

    response = client.post("/api/task-actions/cancel_all")
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "success"
    assert data["task_ids"] == ["task-1", "task-2"]


def test_f5a_outline_creates_task(monkeypatch, tmp_path):
    fake_code_dir = _prepare_fake_script_dir(tmp_path, "f5a_llm_chapter_outline.py")
    routeworkflow.TASKS.clear()

    monkeypatch.setattr(routeworkflow, "CODE_DIR", str(fake_code_dir))
    monkeypatch.setattr(routeworkflow, "run_task_safely_pool", _noop_async)
    monkeypatch.setattr(routeworkflow, "save_and_prune_tasks_async", _noop_async)

    response = client.post(
        "/api/scripts/f5a_outline",
        json={
            "project_name": "demo_project",
            "chapter_name": "第一章",
            "chapter_brief": "测试大纲",
            "model": "deepseek-chat",
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "started"
    assert "task_id" in data
    assert routeworkflow.TASKS[data["task_id"]]["type"] == "f5a"


def test_f5b_generate_rejects_blank_project_name():
    response = client.post(
        "/api/scripts/f5b_generate",
        json={
            "project_name": "   ",
            "chapter_name": "第一章",
            "model": "deepseek-chat",
        },
    )

    assert response.status_code == 403


def test_f4a_completion_creates_task(monkeypatch, tmp_path):
    fake_code_dir = _prepare_fake_script_dir(tmp_path, "f4a_llm_setting_completion.py")
    routeworkflow.TASKS.clear()

    monkeypatch.setattr(routeworkflow, "CODE_DIR", str(fake_code_dir))
    monkeypatch.setattr(routeworkflow, "run_task_safely_pool", _noop_async)
    monkeypatch.setattr(routeworkflow, "save_and_prune_tasks_async", _noop_async)

    response = client.post(
        "/api/scripts/f4a_completion",
        json={
            "target_file": "",
            "mode": "worldview",
            "project_name": "demo_project",
            "form_data": {"worldview": "test"},
            "model": "deepseek-chat",
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "started"
    assert routeworkflow.TASKS[data["task_id"]]["type"] == "f4a"
