import os
import json
import asyncio
import uuid
import shutil
import sys
import re
import base64
from datetime import datetime

from fastapi import APIRouter, HTTPException, Header, UploadFile, File

from .config import CODE_DIR, REF_DIR, STYLE_DIR, PROJ_DIR
from .models import SettingCompletionRequest, ChapterOutlineRequest, NovelGenerationRequest

from core._core_utils import (
    resolve_sandbox_path, 
    mask_sensitive_info, 
    validate_safe_param
)
from .tasks import (
    TASKS,
    add_task_safe,
    cancel_all_tasks,
    cancel_latest_task,
    load_tasks_safe,
    run_task_safely_pool,
    save_and_prune_tasks_async,
)

router = APIRouter()
load_tasks_safe() 

@router.get("/api/references")
async def get_references():
    return [f for f in os.listdir(REF_DIR) if os.path.isfile(os.path.join(REF_DIR, f))]

@router.post("/api/references/upload")
async def upload_reference(file: UploadFile = File(...)):
    try:
        safe_filename = os.path.basename(file.filename)
        if not safe_filename:
            raise ValueError("文件名无效或未被系统正确接收")
        name, ext = os.path.splitext(safe_filename)
        allowed_exts = ('.txt', '.md')
        if ext.lower() not in allowed_exts:
            raise ValueError(f"安全拦截：仅允许上传 {allowed_exts} 格式的参考文本")
        if len(name) > 80:
            safe_filename = name[:80] + ext
        file_path = os.path.join(REF_DIR, safe_filename)
        
        def _write_uploaded_file():
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
                
        await asyncio.to_thread(_write_uploaded_file)
        return {"status": "success", "filename": safe_filename}
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except OSError as oe:
        raise HTTPException(status_code=500, detail="文件系统存储阶段发生读写异常或权限被拒")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=mask_sensitive_info(str(e)))

@router.get("/api/tasks")
async def list_tasks():
    sorted_tasks = sorted(TASKS.items(), key=lambda x: x[1].get('start_time') or x[1].get('created_at', ''), reverse=True)
    return [{"id": k, **v} for k, v in sorted_tasks[:20]]


@router.post("/api/task-actions/cancel_latest")
async def cancel_latest_task_action():
    result = await cancel_latest_task()
    if not result:
        return {"status": "noop", "message": "当前没有可终止任务"}
    if result.get("already_finished"):
        return {
            "status": "noop",
            "message": f"最近任务已结束：{result['task_name']}",
            "task_id": result["task_id"],
        }
    return {
        "status": "success",
        "message": f"已终止最近任务：{result['task_name']}",
        "task_id": result["task_id"],
    }


@router.post("/api/task-actions/cancel_all")
async def cancel_all_tasks_action():
    results = await cancel_all_tasks()
    if not results:
        return {"status": "noop", "message": "当前没有可终止任务", "task_ids": []}
    return {
        "status": "success",
        "message": f"已终止 {len(results)} 个任务",
        "task_ids": [item["task_id"] for item in results],
    }

@router.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/api/tasks/cancel_latest")
async def cancel_latest_task_route():
    result = await cancel_latest_task()
    if not result:
        return {"status": "noop", "message": "当前没有可终止任务"}
    if result.get("already_finished"):
        return {
            "status": "noop",
            "message": f"最近任务已结束：{result['task_name']}",
            "task_id": result["task_id"],
        }
    return {
        "status": "success",
        "message": f"已终止最近任务：{result['task_name']}",
        "task_id": result["task_id"],
    }


@router.post("/api/tasks/cancel_all")
async def cancel_all_tasks_route():
    results = await cancel_all_tasks()
    if not results:
        return {"status": "noop", "message": "当前没有可终止任务", "task_ids": []}
    return {
        "status": "success",
        "message": f"已终止 {len(results)} 个任务",
        "task_ids": [item["task_id"] for item in results],
    }

@router.post("/api/scripts/f4a_completion")
async def run_f4a_completion(req: SettingCompletionRequest, x_api_key: str = Header(None)):
    try:
        project_name = validate_safe_param(req.project_name)
        mode = validate_safe_param(req.mode)
        model = validate_safe_param(req.model)
        
        script_path = os.path.join(CODE_DIR, "scripts", "f4a_llm_setting_completion.py")
        if not os.path.exists(script_path):
            return {"error": f"未找到执行脚本"}
            
        target_path = ""
        if req.target_file and req.target_file.strip():
            try:
                target_path = resolve_sandbox_path(REF_DIR, req.target_file, allowed_extensions=('.txt', '.md', '.json'))
            except (ValueError, PermissionError) as e:
                raise HTTPException(status_code=403, detail=mask_sensitive_info(str(e)))

        json_string = json.dumps(req.form_data, ensure_ascii=False)
        b64_json = base64.b64encode(json_string.encode('utf-8')).decode('utf-8')
        
        task_id = str(uuid.uuid4())
        
        kwargs = {
            "target_file": target_path,
            "mode": mode,
            "json_data": f"b64:{b64_json}",  
            "project": project_name,   
            "model": model
        }
        
        ref_file_display = os.path.basename(req.target_file) if req.target_file else "无参考原创"
        
        await add_task_safe(task_id, {
            "name": f"f4a [{model}]: {mode} - {ref_file_display}",
            "type": "f4a",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "ref_file": ref_file_display
        })
        
        asyncio.create_task(save_and_prune_tasks_async()) 
        asyncio.create_task(run_task_safely_pool(task_id, "scripts.f4a_llm_setting_completion", "run_headless", kwargs, x_api_key))
        return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f4a ({mode}模式)"}
        
    except ValueError as e: 
        raise HTTPException(status_code=403, detail=mask_sensitive_info(str(e))) 
    except OSError as e:
        raise HTTPException(status_code=500, detail=mask_sensitive_info(str(e)))

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
        b64_brief = base64.b64encode(brief_json.encode('utf-8')).decode('utf-8')
        
        kwargs = {
            "project": project_name, 
            "chapter": chapter_name, 
            "brief": f"b64:{b64_brief}",     
            "model": model
        }
        
        task_id = str(uuid.uuid4())
        await add_task_safe(task_id, {
            "name": f"f5a [{model}]: {project_name} - {chapter_name}",
            "type": "f5a",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "ref_file": project_name
        })

        asyncio.create_task(save_and_prune_tasks_async())
        asyncio.create_task(run_task_safely_pool(task_id, "scripts.f5a_llm_chapter_outline", "run_headless", kwargs, x_api_key))
        return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f5a 生成大纲"}
        
    except ValueError as e:
        raise HTTPException(status_code=403, detail=mask_sensitive_info(str(e)))
    except OSError as e:
        raise HTTPException(status_code=500, detail=mask_sensitive_info(str(e)))

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
            except OSError:
                pass
            except json.JSONDecodeError:
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
            raise RuntimeError(f"包组装异常: {stderr.decode('utf-8', errors='replace')}")
            
        return {"prompt": stdout.decode('utf-8', errors='replace')}
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=mask_sensitive_info(str(e)))
    except (OSError, RuntimeError) as e:
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
        
        kwargs = {
            "project": project_name,
            "chapter": chapter_name,
            "model": model,
            "export_prompt_only": False
        }

        task_id = str(uuid.uuid4())
        await add_task_safe(task_id, {
            "name": f"f5b [{model}]: {project_name} - {chapter_name}",
            "type": "f5b",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "ref_file": project_name
        })
        
        asyncio.create_task(save_and_prune_tasks_async())
        asyncio.create_task(run_task_safely_pool(task_id, "scripts.f5b_llm_novel_generation", "run_headless", kwargs, x_api_key)) 
        return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f5b 正文生成"}
        
    except ValueError as e:
        raise HTTPException(status_code=403, detail=mask_sensitive_info(str(e)))
    except OSError as e:
        raise HTTPException(status_code=500, detail=mask_sensitive_info(str(e)))

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
        if character:
            character = re.sub(r'[\\/:\*\?"<>|]', '', character).strip()
        if chapter_name:
            chapter_name = re.sub(r'[\\/:\*\?"<>|]', '', chapter_name).strip()

        script_type = validate_safe_param(script_type)
        project_name = validate_safe_param(project_name)
        character = validate_safe_param(character)
        chapter_name = validate_safe_param(chapter_name)
        model = validate_safe_param(model)
        
        if script_type == "f3c" and not character:
            raise ValueError("角色名为空或因包含非法字符被清洗，请提供有效的纯文本角色名")
            
        script_map = { 
            "f0": "f0_local_vector_indexer", 
            "f1a": "f1a_local_text_stats", 
            "f1b": "f1b_llm_style_feature", 
            "f2a": "f2a_local_word_freq", 
            "f2b": "f2b_llm_keyword_base", 
            "f3a": "f3a_llm_exclusive_vocab", 
            "f3b": "f3b_llm_worldview", 
            "f3c": "f3c_llm_character", 
            "f4b": "f4b_llm_plot_compression", 
            "f4c": "f4c_local_project_rag", 
            "f5a": "f5a_llm_chapter_outline", 
            "f5b": "f5b_llm_novel_generation", 
            "f6":  "f6_llm_plot_deduction", 
            "f7":  "f7_llm_text_validation" 
        } 
         
        script_name = script_map.get(script_type) 
        if not script_name: 
            return {"error": f"未知的脚本类型或该模块需走专用路由: {script_type}"} 
             
        script_path = os.path.join(CODE_DIR, "scripts", f"{script_name}.py") 
        if not os.path.exists(script_path): 
            return {"error": f"系统拦截：未找到物理脚本"} 
        
        target_path = "" 
        if target_file: 
            target_path = resolve_sandbox_path(REF_DIR, target_file, allowed_extensions=('.txt', '.md', '.json', '.index')) 
            
        target_name = os.path.basename(target_file) if target_file else "无目标文件" 
        if script_type == "f3c" and character: 
            target_name += f" ({character})" 
        if script_type == "f4c" and project_name:
            target_name = f"工程前文库 [{project_name}]"
            
        novel_name = os.path.splitext(os.path.basename(target_file))[0] if target_file else "" 
        style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation") 
        
        f3c_main_name = None
        if character:
            f3c_main_name = re.split(r'[\(（]', character)[0].strip()
         
        check_file_map = { 
            "f0": os.path.join(style_dir, "global_rag_db", "vector.index"), 
            "f1a": os.path.join(style_dir, "statistics", "统计指标.txt"), 
            "f1b": os.path.join(style_dir, "features.md"), 
            "f2a": os.path.join(style_dir, "statistics", "高频词.txt"), 
            "f2b": os.path.join(style_dir, "positive_words.md"), 
            "f3a": os.path.join(style_dir, "exclusive_vocab.md"), 
            "f3b": os.path.join(style_dir, "world_settings.md"), 
            "f3c": os.path.join(style_dir, "character_profiles", f"{f3c_main_name}.md") if f3c_main_name else None, 
            "f4b": os.path.join(style_dir, "hierarchical_rag_db", "chunks.json") 
        } 
         
        target_output = check_file_map.get(script_type) 
        if not force and target_output and os.path.exists(target_output) and os.path.getsize(target_output) > 10: 
            task_id = str(uuid.uuid4()) 
            await add_task_safe(task_id, { 
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
            }) 
            asyncio.create_task(save_and_prune_tasks_async())
            return {"status": "started", "task_id": task_id, "message": "检测到缓存，已自动跳过"} 
        
        task_id = str(uuid.uuid4()) 
        await add_task_safe(task_id, { 
            "name": f"{script_type} [{model if script_type != 'f4c' else 'local'}]: {target_name}", 
            "type": script_type, 
            "status": "pending", 
            "created_at": datetime.now().isoformat(), 
            "ref_file": target_name 
        }) 

        kwargs = {}
        if script_type in ["f0", "f1a", "f2a"]:
            kwargs = {"target_file": target_path}
        elif script_type in ["f1b", "f2b", "f3a", "f3b"]:
            kwargs = {"target_file": target_path, "project": project_name, "model": model} 
        elif script_type == "f3c":
            if not character: 
                raise ValueError("执行 f3c 时必须传递 character 参数") 
            kwargs = {"target_file": target_path, "character": character, "project": project_name, "model": model} 
        elif script_type == "f4b":
            kwargs = {"target_file": target_path, "project": project_name} 
        elif script_type == "f7":
            kwargs = {"project": project_name, "script_type": "f5b", "chapter": chapter_name, "mode": "loose"} 

        script_module = f"scripts.{script_name}"
        asyncio.create_task(save_and_prune_tasks_async())
        asyncio.create_task(run_task_safely_pool(task_id, script_module, "run_headless", kwargs, x_api_key)) 
        return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: {script_type}"}

    except ValueError as e: 
        raise HTTPException(status_code=403, detail=mask_sensitive_info(str(e)))
    except OSError as e:
        raise HTTPException(status_code=500, detail=mask_sensitive_info(str(e)))
