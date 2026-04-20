import sys
from pathlib import Path

from fastapi.testclient import TestClient


CODE_DIR = Path(__file__).resolve().parents[1] / "style_imitation_code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from main import app  # noqa: E402
from api import routeproject  # noqa: E402


client = TestClient(app)


def test_create_project_success(monkeypatch, tmp_path):
    proj_dir = tmp_path / "novel_projects"
    style_dir = tmp_path / "styles"
    proj_dir.mkdir()
    style_dir.mkdir()

    ref_style = style_dir / "demo_style"
    ref_style.mkdir()
    (ref_style / "features.md").write_text("features", encoding="utf-8")
    (ref_style / "positive_words.md").write_text("positive", encoding="utf-8")
    (ref_style / "negative_words.md").write_text("negative", encoding="utf-8")

    monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
    monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

    response = client.post(
        "/api/projects",
        json={
            "name": "demo_book",
            "branch": "原创",
            "reference_style": "demo_style",
        },
    )

    created_dir = proj_dir / "demo_book_style_imitation"
    content_dir = created_dir / "content"

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert created_dir.exists()
    assert content_dir.exists()
    assert any(path.suffix == ".txt" for path in content_dir.iterdir())


def test_create_chapter_conflict_returns_409(monkeypatch, tmp_path):
    proj_dir = tmp_path / "novel_projects"
    style_dir = tmp_path / "styles"
    content_dir = proj_dir / "demo_project" / "content"
    content_dir.mkdir(parents=True)
    style_dir.mkdir()
    (content_dir / "第一章.txt").write_text("existing", encoding="utf-8")

    monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
    monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

    response = client.post("/api/projects/demo_project/chapters/第一章")

    assert response.status_code == 409
    assert response.json()["detail"] == "FILE_EXISTS"


def test_update_and_get_chapter_content(monkeypatch, tmp_path):
    proj_dir = tmp_path / "novel_projects"
    style_dir = tmp_path / "styles"
    content_dir = proj_dir / "demo_project" / "content"
    content_dir.mkdir(parents=True)
    style_dir.mkdir()
    (content_dir / "第一章.txt").write_text("", encoding="utf-8")

    monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
    monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

    update_response = client.put(
        "/api/projects/demo_project/chapters/第一章/content",
        json={"content": "这是测试内容"},
    )
    read_response = client.get("/api/projects/demo_project/chapters/第一章/content")

    assert update_response.status_code == 200
    assert update_response.json()["status"] == "success"
    assert read_response.status_code == 200
    assert read_response.json()["content"] == "这是测试内容"
