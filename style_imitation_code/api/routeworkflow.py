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

from core._core_utils import (
    resolve_sandbox_path, 
    create_sandbox_ticket, 
    cleanup_sandbox_ticket, 
    mask_sensitive_info, 
    validate_safe_param
)
from .tasks import TASKS, run_task_safely, load_tasks_safe, save_and_prune_tasks_async

router = APIRouter()
load_tasks_safe() 

# 异步守护与沙箱垃圾回收封装
async def run_task_with_cleanup(task_id: str, cmd_list: list, x_api_key: str, ticket_ids: list):
    try:
        await run_task_safely(task_id, cmd_list, x_api_key)
    finally:
        for tid in ticket_ids:
            cleanup_sandbox_ticket(tid)

# ==========================================
# 自动化工作流 API (后台执行调度)
# ==========================================

@router.get("/api/references")
async def get_references():
    return [f for f in os.listdir(REF_DIR) if os.path.isfile(os.path.join(REF_DIR, f))]

@router.post("/api/references/upload")
async def upload_reference(file: UploadFile = File(...)):
    try:
        file_path = os.path.join(REF_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"status": "success", "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=mask_sensitive_info(str(e)))

@router.get("/api/tasks")
async def list_tasks():
    sorted_tasks = sorted(TASKS.items(), key=lambda x: x[1].get('start_time', ''), reverse=True)
    return [{"id": k, **v} for k, v in sorted_tasks[:20]]

@router.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task

@router.post("/api/scripts/f4a_completion")
async def run_f4a_completion(req: SettingCompletionRequest, x_api_key: str = Header(None)):
    try:
        project_name = validate_safe_param(req.project_name)
        mode = validate_safe_param(req.mode)
        model = validate_safe_param(req.model)
        
        script_path = os.path.join(CODE_DIR, "scripts", "f4a_llm_setting_completion.py")
        if not os.path.exists(script_path):
            return {"error": f"未找到执行脚本"}
            
        json_string = json.dumps(req.form_data, ensure_ascii=False)
        
        target_path = resolve_sandbox_path(REF_DIR, req.target_file, allowed_extensions=('.txt', '.md', '.json')) 
        ticket_id = create_sandbox_ticket(target_path)
        
        cmd = [
            sys.executable, script_path, 
            "--target_file", ticket_id,
            "--mode", mode,
            "--json_data", json_string,
            "--model", model
        ]
        if project_name:
            cmd.extend(["--project", project_name])
            
        task_id = str(uuid.uuid4())
        TASKS[task_id] = {
            "name": f"f4a [{model}]: {mode} - {os.path.basename(req.target_file)}",
            "type": "f4a",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "ref_file": os.path.basename(req.target_file)
        }
        
        asyncio.create_task(save_and_prune_tasks_async()) 
        asyncio.create_task(run_task_with_cleanup(task_id, cmd, x_api_key, [ticket_id]))
        return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f4a ({mode}模式)"}
        
    except Exception as e: 
        raise HTTPException(status_code=403, detail=mask_sensitive_info(str(e))) 

@router.post("/api/scripts/f5a_outline")
async def run_f5a_outline(req: ChapterOutlineRequest, x_api_key: str = Header(None)):
    try:
        project_name = validate_safe_param(req.project_name)
        chapter_name = validate_safe_param(req.chapter_name)
        model = validate_safe_param(req.model)
        
        script_path = os.path.join(CODE_DIR, "scripts", "f5a_llm_chapter_outline.py")
        if not os.path.exists(script_path):
            return {"error": f"未找到执行脚本"}
            
        brief_json = json.dumps({"brief": req.chapter_brief}, ensure_ascii=False)
        cmd = [
            sys.executable, script_path, 
            "--project", project_name,
            "--chapter", chapter_name,
            "--brief", brief_json,
            "--model", model
        ]
        
        task_id = str(uuid.uuid4())
        TASKS[task_id] = {
            "name": f"f5a [{model}]: {project_name} - {chapter_name}",
            "type": "f5a",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "ref_file": project_name
        }

        asyncio.create_task(save_and_prune_tasks_async())
        asyncio.create_task(run_task_with_cleanup(task_id, cmd, x_api_key, []))
        return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f5a 生成大纲"}
        
    except Exception as e:
        raise HTTPException(status_code=403, detail=mask_sensitive_info(str(e)))

@router.post("/api/scripts/f5b_prompt_export")
async def export_f5b_prompt(req: NovelGenerationRequest):
    try:
        project_name = validate_safe_param(req.project_name)
        chapter_name = validate_safe_param(req.chapter_name)
        model = validate_safe_param(req.model)
        
        script_path = os.path.join(CODE_DIR, "scripts", "f5b_llm_novel_generation.py")
        if not os.path.exists(script_path):
            raise HTTPException(status_code=404, detail=f"未找到执行脚本")
        
        project_config_path = os.path.join(PROJ_DIR, project_name, "project_config.json")
        branch_mode = "同人" 
        if os.path.exists(project_config_path):
            try:
                with open(project_config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    branch_mode = validate_safe_param(config.get("mode", "同人"))
            except:
                pass

        cmd = [
            sys.executable, script_path, 
            "--project", project_name,
            "--chapter", chapter_name,
            "--model", model,
            "--branch", branch_mode,
            "--export_prompt_only" 
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"包组装异常: {stderr.decode('utf-8', errors='replace')}")
            
        return {"prompt": stdout.decode('utf-8', errors='replace')}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=mask_sensitive_info(str(e)))

@router.post("/api/scripts/f5b_generate")
async def run_f5b_generate(req: NovelGenerationRequest, x_api_key: str = Header(None)):
    try:
        project_name = validate_safe_param(req.project_name)
        chapter_name = validate_safe_param(req.chapter_name)
        model = validate_safe_param(req.model)
        
        script_path = os.path.join(CODE_DIR, "scripts", "f5b_llm_novel_generation.py")
        if not os.path.exists(script_path):
            return {"error": f"未找到执行脚本"}
        
        project_config_path = os.path.join(PROJ_DIR, project_name, "project_config.json")
        branch_mode = "同人" 
        if os.path.exists(project_config_path):
            try:
                with open(project_config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    branch_mode = validate_safe_param(config.get("mode", "同人"))
            except:
                pass

        cmd = [
            sys.executable, script_path, 
            "--project", project_name,
            "--chapter", chapter_name,
            "--model", model,
            "--branch", branch_mode
        ]

        task_id = str(uuid.uuid4())
        TASKS[task_id] = {
            "name": f"f5b [{model}]: {project_name} - {chapter_name}",
            "type": "f5b",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "ref_file": project_name
        }
        
        asyncio.create_task(save_and_prune_tasks_async())
        asyncio.create_task(run_task_with_cleanup(task_id, cmd, x_api_key, [])) 
        return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f5b 正文生成"}
        
    except Exception as e:
        raise HTTPException(status_code=403, detail=mask_sensitive_info(str(e)))

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
    try:
        # 白名单防注过滤
        script_type = validate_safe_param(script_type)
        project_name = validate_safe_param(project_name)
        character = validate_safe_param(character)
        chapter_name = validate_safe_param(chapter_name)
        model = validate_safe_param(model)
        
        script_map = { 
            "f0": "f0_local_vector_indexer.py", 
            "f1a": "f1a_local_text_stats.py", 
            "f1b": "f1b_llm_style_feature.py", 
            "f2a": "f2a_local_word_freq.py", 
            "f2b": "f2b_llm_keyword_base.py", 
            "f3a": "f3a_llm_exclusive_vocab.py", 
            "f3b": "f3b_llm_worldview.py", 
            "f3c": "f3c_llm_character.py", 
            "f4a": "f4a_llm_setting_completion.py", 
            "f4b": "f4b_llm_plot_compression.py", 
            "f5a": "f5a_llm_chapter_outline.py", 
            "f5b": "f5b_llm_novel_generation.py", 
            "f6":  "f6_llm_plot_deduction.py", 
            "f7":  "f7_llm_text_validation.py" 
        } 
         
        script_name = script_map.get(script_type) 
        if not script_name: 
            return {"error": f"未知的脚本类型或该模块需走专用路由: {script_type}"} 
             
        script_path = os.path.join(CODE_DIR, "scripts", script_name) 
        if not os.path.exists(script_path): 
            return {"error": f"系统拦截：未找到物理脚本"} 
        
        # 沙箱过滤与票据生成
        ticket_id = "" 
        if target_file: 
            target_path = resolve_sandbox_path(REF_DIR, target_file, allowed_extensions=('.txt', '.md', '.json', '.index')) 
            ticket_id = create_sandbox_ticket(target_path)
            
        target_name = os.path.basename(target_file) if target_file else "无目标文件" 
        if script_type == "f3c" and character: 
            target_name += f" ({character})" 
            
        # ======================================================== 
        # 一键流水线 断点检索与跳过机制 
        # ======================================================== 
        novel_name = os.path.splitext(os.path.basename(target_file))[0] if target_file else "" 
        style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation") 
         
        check_file_map = { 
            "f0": os.path.join(style_dir, "global_rag_db", "vector.index"), 
            "f1a": os.path.join(style_dir, "statistics", "统计指标.txt"), 
            "f1b": os.path.join(style_dir, "features.md"), 
            "f2a": os.path.join(style_dir, "statistics", "高频词.txt"), 
            "f2b": os.path.join(style_dir, "positive_words.md"), 
            "f3a": os.path.join(style_dir, "exclusive_vocab.md"), 
            "f3b": os.path.join(style_dir, "world_settings.md"), 
            "f3c": os.path.join(style_dir, "character_profiles", f"{character}.md") if character else None, 
            "f4b": os.path.join(style_dir, "hierarchical_rag_db", "chunks.json") 
        } 
         
        target_output = check_file_map.get(script_type) 
        if not force and target_output and os.path.exists(target_output) and os.path.getsize(target_output) > 10: 
            task_id = str(uuid.uuid4()) 
            TASKS[task_id] = { 
                "name": f"[INFO] [缓存跳过] {script_type} [{model}]: {target_name}", 
                "type": script_type, 
                "status": "success", 
                "start_time": datetime.now().isoformat(), 
                "created_at": datetime.now().isoformat(), 
                "end_time": datetime.now().isoformat(), 
                "ref_file": target_name, 
                "stdout": f"检测到本地已存在产物，自动跳过执行。", 
                "stderr": "", 
                "tokens": 0 
            } 
            asyncio.create_task(save_and_prune_tasks_async())
            # 命中缓存提前阻断，在此处强制清理沙箱废票
            if ticket_id:
                cleanup_sandbox_ticket(ticket_id)
            return {"status": "started", "task_id": task_id, "message": "检测到缓存，已自动跳过"} 
        # ======================================================== 
        
        cmd = [sys.executable, script_path] 
        # 传入票据而非明文路径
        if ticket_id:
            cmd.extend(["--target_file", ticket_id])
            
        if project_name: 
            cmd.extend(["--project", project_name]) 
         
        if script_type in ["f1b", "f2b", "f3a", "f3b", "f3c", "f4a", "f5a", "f5b", "f6", "f7"]: 
            cmd.extend(["--model", model]) 
             
        if script_type == "f3c": 
            if not character: 
                raise ValueError("执行 f3c 时必须传递 character 参数") 
            cmd.extend(["--character", character]) 
             
        if chapter_name and script_type in ["f5a", "f5b", "f7"]: 
            cmd.extend(["--chapter", chapter_name]) 
         
        task_id = str(uuid.uuid4()) 
        TASKS[task_id] = { 
            "name": f"{script_type} [{model}]: {target_name}", 
            "type": script_type, 
            "status": "pending", 
            "created_at": datetime.now().isoformat(), 
            "ref_file": target_name 
        } 
        
        asyncio.create_task(save_and_prune_tasks_async())
        # 在闭包中执行，确保沙箱生命周期与命令同步
        asyncio.create_task(run_task_with_cleanup(task_id, cmd, x_api_key, [ticket_id] if ticket_id else [])) 
        return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: {script_name}"}

    except Exception as e: 
        raise HTTPException(status_code=403, detail=mask_sensitive_info(str(e)))