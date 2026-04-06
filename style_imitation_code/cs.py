import os
import json
import asyncio
import uuid
import shutil
import sys
from datetime import datetime

from fastapi import APIRouter, HTTPException, Header, UploadFile, File
from fastapi.responses import StreamingResponse

from .config import CODE_DIR, REF_DIR, STYLE_DIR, PROJ_DIR
from .models import SettingCompletionRequest, ChapterOutlineRequest, NovelGenerationRequest
from core._core_utils import resolve_sandbox_path 
# 引用升级后的方法
from .tasks import TASKS, add_task_safe, run_task_safely_pool, load_tasks_safe, save_and_prune_tasks_async

router = APIRouter()
load_tasks_safe() 

# （...保持其他无需变更的上传/检索API不变，仅修改以下任务调度路由...）

@router.post("/api/scripts/f4a_completion")
async def run_f4a_completion(req: SettingCompletionRequest, x_api_key: str = Header(None)):
    try: 
        target_path = resolve_sandbox_path(REF_DIR, req.target_file, allowed_extensions=('.txt', '.md', '.json')) 
    except Exception as e: 
        raise HTTPException(status_code=403, detail=str(e)) 
    
    task_id = str(uuid.uuid4())
    await add_task_safe(task_id, {
        "name": f"f4a [{req.model}]: {req.mode} - {os.path.basename(req.target_file)}",
        "type": "f4a",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "ref_file": os.path.basename(req.target_file)
    })
    
    # 转换为 kwargs 字典进行无缝传递
    kwargs = {
        "target_file": target_path,
        "mode": req.mode,
        "json_string": json.dumps(req.form_data, ensure_ascii=False),
        "project_name": req.project_name,
        "model": req.model
    }
    
    asyncio.create_task(run_task_safely_pool(task_id, "scripts.f4a_llm_setting_completion", "run_headless", kwargs, x_api_key))
    return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f4a ({req.mode}模式)"}

@router.post("/api/scripts/f5a_outline")
async def run_f5a_outline(req: ChapterOutlineRequest, x_api_key: str = Header(None)):
    task_id = str(uuid.uuid4())
    await add_task_safe(task_id, {
        "name": f"f5a [{req.model}]: {req.project_name} - {req.chapter_name}",
        "type": "f5a",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "ref_file": req.project_name
    })

    kwargs = {
        "project_name": req.project_name,
        "chapter_name": req.chapter_name,
        "chapter_brief_json": json.dumps({"brief": req.chapter_brief}, ensure_ascii=False),
        "model": req.model
    }
    asyncio.create_task(run_task_safely_pool(task_id, "scripts.f5a_llm_chapter_outline", "run_headless", kwargs, x_api_key))
    return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f5a 生成大纲"}

# export_f5b_prompt 保持不变，因其直接使用 await asyncio.create_subprocess_exec 并返回 stdout，不涉及常驻内存任务

@router.post("/api/scripts/f5b_generate")
async def run_f5b_generate(req: NovelGenerationRequest, x_api_key: str = Header(None)):
    task_id = str(uuid.uuid4())
    await add_task_safe(task_id, {
        "name": f"f5b [{req.model}]: {req.project_name} - {req.chapter_name}",
        "type": "f5b",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "ref_file": req.project_name
    })

    kwargs = {
        "project_name": req.project_name,
        "chapter_name": req.chapter_name,
        "model": req.model,
        "export_prompt_only": False
    }
    asyncio.create_task(run_task_safely_pool(task_id, "scripts.f5b_llm_novel_generation", "run_headless", kwargs, x_api_key))
    return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f5b 正文生成"}

@router.post("/api/scripts/{script_type}") 
async def run_script( 
    script_type: str, 
    target_file: str = "", 
    project_name: str = "", 
    character: str = "", 
    chapter_name: str = "", 
    model: str = "deepseek-chat", 
    force: bool = False, 
    x_api_key: str = Header(None) 
): 
    # (...保留前期的安全检测及缓存跳过逻辑...)
    # 假设此处通过了缓存校验，准备开始执行

    script_name_map = {
        "f0": "f0_local_vector_indexer", "f1a": "f1a_local_text_stats", "f1b": "f1b_llm_style_feature",
        "f2a": "f2a_local_word_freq", "f2b": "f2b_llm_keyword_base", "f3a": "f3a_llm_exclusive_vocab",
        "f3b": "f3b_llm_worldview", "f3c": "f3c_llm_character", "f4b": "f4b_llm_plot_compression",
        "f7": "f7_llm_text_validation"
    }
    
    if script_type not in script_name_map:
        return {"error": f"未知的脚本类型或模块: {script_type}"}

    target_name = os.path.basename(target_file) if target_file else "无目标文件" 
    if script_type == "f3c" and character: target_name += f" ({character})" 
    
    task_id = str(uuid.uuid4()) 
    await add_task_safe(task_id, { 
        "name": f"{script_type} [{model}]: {target_name}", 
        "type": script_type, 
        "status": "pending", 
        "created_at": datetime.now().isoformat(), 
        "ref_file": target_name 
    }) 

    # 精准映射参数规则，规避 CLI 参数拼接丢失的风险
    kwargs = {}
    if script_type in ["f0", "f1a", "f2a"]:
        kwargs = {"target_file": target_file}
    elif script_type in ["f1b", "f2b", "f3a", "f3b"]:
        kwargs = {"target_file": target_file, "project_name": project_name, "model": model}
    elif script_type == "f3c":
        kwargs = {"target_file": target_file, "character_list_str": character, "project_name": project_name, "model": model}
    elif script_type == "f4b":
        kwargs = {"target_file": target_file, "project_name": project_name}
    elif script_type == "f7":
        kwargs = {"project_name": project_name, "script_type": "f5b", "chapter_name": chapter_name, "mode": "loose"}

    script_module = f"scripts.{script_name_map[script_type]}"
    asyncio.create_task(run_task_safely_pool(task_id, script_module, "run_headless", kwargs, x_api_key)) 
    return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: {script_type}"}