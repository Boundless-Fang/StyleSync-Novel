import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


CODE_DIR = Path(__file__).resolve().parents[1] / "style_imitation_code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from main import app  # noqa: E402
from api import routeproject  # noqa: E402


client = TestClient(app)


def test_create_project_success(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        proj_dir = base_dir / "novel_projects"
        style_dir = base_dir / "styles"
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
                "branch": "original",
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


def test_create_project_rejects_invalid_branch():
    response = client.post(
        "/api/projects",
        json={
            "name": "demo_book",
            "branch": "unsupported",
            "reference_style": "demo_style",
        },
    )

    assert response.status_code == 422


def test_create_project_conflict_returns_409(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        proj_dir = base_dir / "novel_projects"
        style_dir = base_dir / "styles"
        proj_dir.mkdir()
        style_dir.mkdir()
        (proj_dir / "demo_book_style_imitation").mkdir()

        monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
        monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

        response = client.post(
            "/api/projects",
            json={
                "name": "demo_book",
                "branch": "original",
                "reference_style": "",
            },
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "PROJECT_EXISTS"


def test_create_project_force_overwrite_reinitializes_project(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        proj_dir = base_dir / "novel_projects"
        style_dir = base_dir / "styles"
        proj_dir.mkdir()
        style_dir.mkdir()

        ref_style = style_dir / "demo_style"
        ref_style.mkdir()
        (ref_style / "features.md").write_text("features", encoding="utf-8")
        (ref_style / "positive_words.md").write_text("positive", encoding="utf-8")
        (ref_style / "negative_words.md").write_text("negative", encoding="utf-8")

        existing_dir = proj_dir / "demo_book_style_imitation"
        existing_content = existing_dir / "content"
        existing_content.mkdir(parents=True)
        (existing_dir / "stale.txt").write_text("old", encoding="utf-8")
        (existing_content / "old_chapter.txt").write_text("old content", encoding="utf-8")

        monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
        monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

        response = client.post(
            "/api/projects?force_overwrite=true",
            json={
                "name": "demo_book",
                "branch": "original",
                "reference_style": "demo_style",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert not (existing_dir / "stale.txt").exists()
        assert (existing_dir / "content" / "第一章.txt").exists()


def test_create_chapter_conflict_returns_409(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        proj_dir = base_dir / "novel_projects"
        style_dir = base_dir / "styles"
        content_dir = proj_dir / "demo_project" / "content"
        content_dir.mkdir(parents=True)
        style_dir.mkdir()
        (content_dir / "第一章.txt").write_text("existing", encoding="utf-8")

        monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
        monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

        response = client.post("/api/projects/demo_project/chapters/第一章")

        assert response.status_code == 409
        assert response.json()["detail"] == "FILE_EXISTS"


def test_update_and_get_chapter_content(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        proj_dir = base_dir / "novel_projects"
        style_dir = base_dir / "styles"
        content_dir = proj_dir / "demo_project" / "content"
        content_dir.mkdir(parents=True)
        style_dir.mkdir()
        (content_dir / "第一章.txt").write_text("", encoding="utf-8")

        monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
        monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

        update_response = client.put(
            "/api/projects/demo_project/chapters/第一章/content",
            json={"content": "this is test content"},
        )
        read_response = client.get(
            "/api/projects/demo_project/chapters/第一章/content"
        )

        assert update_response.status_code == 200
        assert update_response.json()["status"] == "success"
        assert read_response.status_code == 200
        assert read_response.json()["content"] == "this is test content"


def test_append_to_specific_chapter(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        proj_dir = base_dir / "novel_projects"
        style_dir = base_dir / "styles"
        content_dir = proj_dir / "demo_project" / "content"
        content_dir.mkdir(parents=True)
        style_dir.mkdir()
        (content_dir / "第一章.txt").write_text("chapter one", encoding="utf-8")
        (content_dir / "第二章.txt").write_text("chapter two", encoding="utf-8")

        monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
        monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

        response = client.post(
            "/api/projects/demo_project/append",
            json={"content": "new text", "chapter_name": "第二章"},
        )

        assert response.status_code == 200
        assert (content_dir / "第一章.txt").read_text(encoding="utf-8") == "chapter one"
        assert "new text" in (content_dir / "第二章.txt").read_text(encoding="utf-8")


def test_append_rejects_missing_chapter(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        proj_dir = base_dir / "novel_projects"
        style_dir = base_dir / "styles"
        content_dir = proj_dir / "demo_project" / "content"
        content_dir.mkdir(parents=True)
        style_dir.mkdir()
        (content_dir / "第一章.txt").write_text("chapter one", encoding="utf-8")

        monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
        monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

        response = client.post(
            "/api/projects/demo_project/append",
            json={"content": "new text", "chapter_name": "第二章"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "CHAPTER_NOT_FOUND"


def test_chapter_migration_renames_related_outline_and_prompt_files(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        proj_dir = base_dir / "novel_projects"
        style_dir = base_dir / "styles"
        project_dir = proj_dir / "demo_project"
        content_dir = project_dir / "content"
        outline_dir = project_dir / "chapter_structures"
        prompt_dir = project_dir / "chapter_specific_prompts"
        content_dir.mkdir(parents=True)
        outline_dir.mkdir(parents=True)
        prompt_dir.mkdir(parents=True)
        style_dir.mkdir()

        (content_dir / "chapter_1.txt").write_text("old content", encoding="utf-8")
        (outline_dir / "chapter_1_outline.md").write_text("outline", encoding="utf-8")
        (prompt_dir / "prompt_chapter_1.txt").write_text("prompt", encoding="utf-8")
        (prompt_dir / "prompt_chapter_1_f5c_prefix.txt").write_text("rewrite", encoding="utf-8")

        monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
        monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

        response = client.get("/api/projects/demo_project/chapters")

        assert response.status_code == 200
        assert response.json() == ["第一章.txt"]
        assert (content_dir / "第一章.txt").exists()
        assert not (content_dir / "chapter_1.txt").exists()
        assert (outline_dir / "第一章_outline.md").exists()
        assert not (outline_dir / "chapter_1_outline.md").exists()
        assert (prompt_dir / "prompt_第一章.txt").exists()
        assert not (prompt_dir / "prompt_chapter_1.txt").exists()
        assert (prompt_dir / "prompt_第一章_f5c_prefix.txt").exists()
        assert not (prompt_dir / "prompt_chapter_1_f5c_prefix.txt").exists()


def test_project_settings_reject_path_traversal(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        proj_dir = base_dir / "novel_projects"
        style_dir = base_dir / "styles"
        project_dir = proj_dir / "demo_project"
        project_dir.mkdir(parents=True)
        style_dir.mkdir()

        monkeypatch.setattr(routeproject, "PROJ_DIR", str(proj_dir))
        monkeypatch.setattr(routeproject, "STYLE_DIR", str(style_dir))

        response = client.get("/api/projects/demo_project/settings/..%2F..%2Fsecret.txt")

        assert response.status_code == 200
        assert "越权访问已被拦截" in response.json()["content"]
