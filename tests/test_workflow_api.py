import sys
import tempfile
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


def _prepare_fake_script_dir(base_dir: Path, script_name: str) -> Path:
    code_dir = base_dir / "code"
    scripts_dir = code_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / script_name).write_text("# fake script\n", encoding="utf-8")
    return code_dir


def test_cancel_latest_task_returns_noop(monkeypatch):
    async def fake_cancel_latest():
        return None

    monkeypatch.setattr(routeworkflow, "cancel_latest_task", fake_cancel_latest)

    response = client.post("/api/tasks/cancel_latest")

    assert response.status_code == 200
    assert response.json()["status"] == "noop"


def test_cancel_all_tasks_returns_summary(monkeypatch):
    async def fake_cancel_all():
        return [
            {"task_id": "task-1", "task_name": "f5a demo"},
            {"task_id": "task-2", "task_name": "f5b demo"},
        ]

    monkeypatch.setattr(routeworkflow, "cancel_all_tasks", fake_cancel_all)

    response = client.post("/api/tasks/cancel_all")
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "success"
    assert data["task_ids"] == ["task-1", "task-2"]


def test_upload_reference_rejects_invalid_extension():
    response = client.post(
        "/api/references/upload",
        files={"file": ("demo.pdf", b"fake", "application/pdf")},
    )

    assert response.status_code == 400


def test_f5a_outline_creates_task(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_code_dir = _prepare_fake_script_dir(
            Path(tmp_dir), "f5a_llm_chapter_outline.py"
        )
        routeworkflow.TASKS.clear()

        monkeypatch.setattr(routeworkflow, "CODE_DIR", str(fake_code_dir))
        monkeypatch.setattr(routeworkflow, "run_task_safely_pool", _noop_async)
        monkeypatch.setattr(routeworkflow, "save_and_prune_tasks_async", _noop_async)

        response = client.post(
            "/api/scripts/f5a_outline",
            json={
                "project_name": "demo_project",
                "chapter_name": "chapter_1",
                "chapter_brief": "test outline",
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
            "chapter_name": "chapter_1",
            "model": "deepseek-chat",
        },
    )

    assert response.status_code == 422


def test_f4a_completion_creates_task(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_code_dir = _prepare_fake_script_dir(
            Path(tmp_dir), "f4a_llm_setting_completion.py"
        )
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


def test_f6_preview_returns_501_when_script_not_implemented(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_code_dir = Path(tmp_dir) / "code"
        scripts_dir = fake_code_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "f6_llm_plot_deduction.py").write_text("", encoding="utf-8")

        monkeypatch.setattr(routeworkflow, "CODE_DIR", str(fake_code_dir))

        response = client.post(
            "/api/scripts/f6",
            params={
                "project_name": "demo_project",
                "chapter_name": "chapter_1",
                "model": "deepseek-chat",
            },
        )

    assert response.status_code == 501
    assert "实验性预留接口" in response.json()["detail"]


def test_f7_preview_marks_response_message(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_code_dir = _prepare_fake_script_dir(
            Path(tmp_dir), "f7_llm_text_validation.py"
        )
        routeworkflow.TASKS.clear()

        monkeypatch.setattr(routeworkflow, "CODE_DIR", str(fake_code_dir))
        monkeypatch.setattr(routeworkflow, "run_task_safely_pool", _noop_async)
        monkeypatch.setattr(routeworkflow, "save_and_prune_tasks_async", _noop_async)

        response = client.post(
            "/api/scripts/f7",
            params={
                "project_name": "demo_project",
                "chapter_name": "chapter_1",
                "model": "deepseek-chat",
            },
        )
        data = response.json()

    assert response.status_code == 200
    assert "实验性预览接口" in data["message"]


def test_f7_requires_chapter_name():
    response = client.post(
        "/api/scripts/f7",
        params={
            "project_name": "demo_project",
            "chapter_name": "",
            "model": "deepseek-chat",
        },
    )

    assert response.status_code == 403
