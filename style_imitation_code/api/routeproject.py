import json
import os
import shutil
from datetime import datetime

from fastapi import APIRouter, HTTPException

from .config import PROJ_DIR, STYLE_DIR
from .models import AppendContent, ChapterUpdate, ProjectCreate, SettingUpdate
from core._core_utils import async_append_text, async_atomic_write, async_smart_read_text

router = APIRouter()


def get_real_dir(proj_name: str):
    if proj_name.startswith("style@@"):
        return os.path.join(STYLE_DIR, proj_name.replace("style@@", ""))
    return os.path.join(PROJ_DIR, proj_name)


def get_validated_target_path(proj_name: str, file_path: str) -> str:
    raw_base_dir = get_real_dir(proj_name)
    safe_base_dir = os.path.realpath(os.path.abspath(raw_base_dir))

    if proj_name.startswith("style@@"):
        expected_root = os.path.realpath(os.path.abspath(STYLE_DIR))
    else:
        expected_root = os.path.realpath(os.path.abspath(PROJ_DIR))

    norm_root = os.path.normcase(expected_root)
    norm_base = os.path.normcase(safe_base_dir)

    try:
        if os.path.commonpath([norm_root, norm_base]) != norm_root:
            raise HTTPException(status_code=403, detail="非法项目名，越权访问被拦截")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="跨盘符项目路径非法") from exc

    target_path = os.path.realpath(os.path.abspath(os.path.join(safe_base_dir, file_path)))
    norm_target = os.path.normcase(target_path)

    try:
        if os.path.commonpath([norm_base, norm_target]) != norm_base:
            raise ValueError("检测到目录穿越")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=f"越权访问被拦截: {exc}") from exc

    return target_path


def build_project_name(project_name: str) -> str:
    base_name = project_name.strip()
    if not base_name.endswith("_style_imitation"):
        return f"{base_name}_style_imitation"
    return base_name


def init_project_structure(target_proj_dir: str, proj: ProjectCreate) -> None:
    for folder in ["content", "character_profiles", "chapter_structures"]:
        os.makedirs(os.path.join(target_proj_dir, folder), exist_ok=True)

    config_path = os.path.join(target_proj_dir, "project_config.json")
    project_config = {
        "name": proj.name,
        "mode": proj.branch,
        "reference_style": proj.reference_style,
        "created_at": datetime.now().isoformat(),
    }
    with open(config_path, "w", encoding="utf-8") as file:
        json.dump(project_config, file, ensure_ascii=False, indent=2)


def init_fanfic_project(target_proj_dir: str, src_style_dir: str) -> None:
    if not src_style_dir or not os.path.exists(src_style_dir):
        raise ValueError("同人模式必须选择有效的参考文风库")

    for filename in [
        "features.md",
        "world_settings.md",
        "plot_outlines.md",
        "positive_words.md",
        "negative_words.md",
        "exclusive_vocab.md",
    ]:
        src_file = os.path.join(src_style_dir, filename)
        if os.path.exists(src_file):
            shutil.copy2(src_file, os.path.join(target_proj_dir, filename))

    for folder in ["character_profiles", "hierarchical_rag_db"]:
        src_folder = os.path.join(src_style_dir, folder)
        if os.path.exists(src_folder):
            dst_folder = os.path.join(target_proj_dir, folder)
            if os.path.exists(dst_folder):
                shutil.rmtree(dst_folder)
            shutil.copytree(src_folder, dst_folder)


def init_original_project(target_proj_dir: str, src_style_dir: str) -> None:
    if not src_style_dir or not os.path.exists(src_style_dir):
        raise ValueError("原创模式必须选择有效的参考文风库")

    for filename in ["features.md", "positive_words.md", "negative_words.md"]:
        src_file = os.path.join(src_style_dir, filename)
        if os.path.exists(src_file):
            shutil.copy2(src_file, os.path.join(target_proj_dir, filename))

    world_settings_path = os.path.join(target_proj_dir, "world_settings.md")
    open(world_settings_path, "w", encoding="utf-8").close()


def ensure_required_files(target_proj_dir: str) -> None:
    required_files = [
        "features.md",
        "world_settings.md",
        "positive_words.md",
        "negative_words.md",
    ]
    for filename in required_files:
        file_path = os.path.join(target_proj_dir, filename)
        if not os.path.exists(file_path):
            open(file_path, "w", encoding="utf-8").close()

    first_chapter_path = os.path.join(target_proj_dir, "content", "第一章.txt")
    with open(first_chapter_path, "w", encoding="utf-8") as file:
        file.write("这里是小说的开头...")


@router.get("/api/projects")
async def get_projects():
    return [f for f in os.listdir(PROJ_DIR) if os.path.isdir(os.path.join(PROJ_DIR, f))]


@router.get("/api/styles")
async def get_styles():
    if not os.path.exists(STYLE_DIR):
        return []
    return [f for f in os.listdir(STYLE_DIR) if os.path.isdir(os.path.join(STYLE_DIR, f))]


@router.post("/api/projects")
async def create_project(proj: ProjectCreate):
    dir_name = build_project_name(proj.name)
    target_proj_dir = os.path.join(PROJ_DIR, dir_name)
    src_style_dir = os.path.join(STYLE_DIR, proj.reference_style) if proj.reference_style else None

    def _execute_project_initialization():
        init_project_structure(target_proj_dir, proj)

        if proj.branch == "同人":
            init_fanfic_project(target_proj_dir, src_style_dir)
        elif proj.branch == "原创":
            init_original_project(target_proj_dir, src_style_dir)

        ensure_required_files(target_proj_dir)

    try:
        import asyncio

        await asyncio.to_thread(_execute_project_initialization)
        return {"status": "success"}
    except ValueError as exc:
        return {"error": str(exc)}
    except OSError as exc:
        print(f"[ERROR] 项目初始化失败: {exc}")
        raise HTTPException(status_code=500, detail="项目创建遇到存储层异常") from exc


@router.get("/api/projects/{proj_name}/chapters")
async def get_chapters(proj_name: str):
    content_dir = os.path.join(PROJ_DIR, proj_name, "content")
    if not os.path.exists(content_dir):
        return []
    return [f for f in os.listdir(content_dir) if f.endswith(".txt")]


@router.get("/api/projects/{proj_name}/characters")
async def get_characters(proj_name: str):
    base_dir = get_real_dir(proj_name)
    char_dir = os.path.join(base_dir, "character_profiles")
    if not os.path.exists(char_dir):
        return []
    return [os.path.splitext(f)[0] for f in os.listdir(char_dir) if f.endswith(".md")]


@router.post("/api/projects/{proj_name}/chapters/{chap_name}")
async def create_or_rename_chapter(proj_name: str, chap_name: str, new_name: str = None, force_overwrite: bool = False):
    content_dir = os.path.join(PROJ_DIR, proj_name, "content")

    target_name = new_name if new_name else chap_name
    target_path = os.path.join(content_dir, f"{target_name}.txt")
    source_path = os.path.join(content_dir, f"{chap_name}.txt")

    if os.path.exists(target_path) and not force_overwrite:
        if new_name and source_path == target_path:
            return {"status": "success"}
        raise HTTPException(status_code=409, detail="FILE_EXISTS")

    def _execute_chapter_fs_modification():
        if new_name:
            if source_path != target_path:
                max_retries = 10
                base_delay = 0.2
                for attempt in range(max_retries):
                    try:
                        os.replace(source_path, target_path)
                        break
                    except PermissionError as exc:
                        if attempt < max_retries - 1:
                            import random
                            import time

                            time.sleep(base_delay * (1.5 ** attempt) + random.uniform(0, 0.1))
                        else:
                            raise PermissionError("目标文件被系统或外部进程占用，超过重试上限") from exc
        else:
            with open(target_path, "w", encoding="utf-8"):
                pass

    try:
        import asyncio

        await asyncio.to_thread(_execute_chapter_fs_modification)
        return {"status": "success"}
    except PermissionError as exc:
        print(f"[ERROR] 章节覆盖失败: {exc}")
        raise HTTPException(status_code=500, detail="文件操作失败，目标文件正被其他进程占用") from exc
    except OSError as exc:
        print("[ERROR] 章节操作失败: 存储层异常")
        raise HTTPException(status_code=500, detail="执行章节文件操作时发生异常") from exc


@router.get("/api/projects/{proj_name}/chapters/{chap_name}/content")
async def get_chapter_content(proj_name: str, chap_name: str):
    filepath = get_validated_target_path(proj_name, f"content/{chap_name}.txt")

    if os.path.exists(filepath):
        try:
            content = await async_smart_read_text(filepath)
            return {"content": content}
        except OSError as exc:
            raise HTTPException(status_code=500, detail="文件读取失败或已被其他线程占用") from exc
    return {"content": ""}


@router.put("/api/projects/{proj_name}/chapters/{chap_name}/content")
async def update_chapter_content(proj_name: str, chap_name: str, update: ChapterUpdate):
    filepath = get_validated_target_path(proj_name, f"content/{chap_name}.txt")

    try:
        await async_atomic_write(filepath, update.content, "text")
        return {"status": "success"}
    except OSError as exc:
        raise HTTPException(status_code=500, detail="保存章节内容失败：存储层异常") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="保存章节内容失败：并发写盘超过重试上限") from exc


@router.post("/api/projects/{proj_name}/append")
async def append_to_novel(proj_name: str, req: AppendContent):
    content_dir = os.path.join(PROJ_DIR, proj_name, "content")
    if not os.path.exists(content_dir):
        return {"error": "未找到章节内容目录"}

    chapters = [f for f in os.listdir(content_dir) if f.endswith(".txt")]
    if not chapters:
        return {"error": "未找到章节文件"}

    target_file = os.path.join(content_dir, chapters[0])
    try:
        await async_append_text(target_file, "\n\n" + req.content)
        return {"status": "success"}
    except OSError as exc:
        raise HTTPException(status_code=500, detail="追加内容失败: 底层I/O锁定") from exc


@router.get("/api/projects/{proj_name}/settings/{file_path:path}")
async def get_project_setting(proj_name: str, file_path: str):
    try:
        target_path = get_validated_target_path(proj_name, file_path)
    except HTTPException as exc:
        return {"content": exc.detail}

    if not os.path.isfile(target_path):
        return {"content": "文件不存在或尚未生成，请检查工作流执行状态"}

    try:
        content = await async_smart_read_text(target_path)
        return {"content": content}
    except OSError:
        return {"content": "系统错误：文件读取异常或被占用"}


@router.put("/api/projects/{proj_name}/settings/{file_path:path}")
async def update_project_setting(proj_name: str, file_path: str, update: SettingUpdate):
    target_path = get_validated_target_path(proj_name, file_path)

    if os.path.isdir(target_path):
        raise HTTPException(status_code=400, detail="目标路径已被文件夹占用，无法写入")

    try:
        import asyncio

        await asyncio.to_thread(os.makedirs, os.path.dirname(target_path), exist_ok=True)
        await async_atomic_write(target_path, update.content, "text")
        return {"status": "success"}
    except OSError as exc:
        raise HTTPException(status_code=500, detail="目录构建或文件写入时发生I/O异常") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="文件并发写盘超过重试上限") from exc


@router.get("/api/projects/{proj_name}/outlines")
async def get_outlines(proj_name: str):
    base_dir = get_real_dir(proj_name)
    outline_dir = os.path.join(base_dir, "chapter_structures")
    if not os.path.exists(outline_dir):
        return []
    return [f for f in os.listdir(outline_dir) if f.endswith(".md") or f.endswith(".json")]


@router.get("/api/projects/{proj_name}/phase1_status")
async def check_phase1_status(proj_name: str):
    base_dir = get_real_dir(proj_name)
    target_file = os.path.join(base_dir, "world_settings.md")
    is_done = os.path.exists(target_file) and os.path.getsize(target_file) > 50
    return {"is_done": is_done}


@router.get("/api/projects/{proj_name}/prompts")
async def get_prompts(proj_name: str):
    base_dir = get_real_dir(proj_name)
    prompt_dir = os.path.join(base_dir, "chapter_specific_prompts")
    if not os.path.exists(prompt_dir):
        return []
    return [f for f in os.listdir(prompt_dir) if f.endswith(".txt")]
