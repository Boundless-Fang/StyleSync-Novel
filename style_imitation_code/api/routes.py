import os
import json
import asyncio
import uuid
import re
import random
import shutil
import sys
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Header, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from openai import AsyncOpenAI

# 引入模型库以驻留主进程
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

# 引入我们刚刚拆分出的配置、模型和任务调度器
from .config import CODE_DIR, REF_DIR, STYLE_DIR, PROJ_DIR, DICT_DIR, TEST_DIR
from .models import (ChatRequest, ProjectCreate, ChapterUpdate, AppendContent, 
                     SettingUpdate, SettingCompletionRequest, ChapterOutlineRequest, 
                     NovelGenerationRequest)
# 引入新分离出的后台锁和流式锁
from .tasks import TASKS, background_semaphore, stream_semaphore, run_task_safely

router = APIRouter()

# =====================================================================
# 全局常驻内存的 Embedding 模型服务生命周期与内部路由
# =====================================================================
class EmbedRequest(BaseModel):
    texts: list[str]

GLOBAL_EMBEDDER = None

@router.on_event("startup")
async def load_embedder():
    global GLOBAL_EMBEDDER
    print("🚀 正在预热加载全局 Embedding 模型 (BAAI/bge-m3)...")
    # 整个 FastAPI 生命周期内仅实例化一次，常驻内存，耗时仅发生在启动阶段
    GLOBAL_EMBEDDER = SentenceTransformer('BAAI/bge-m3')
    print("✅ 全局 Embedding 模型加载完成，子进程 RAG 调用将实现毫秒级响应！")

@router.post("/api/internal/embed")
async def internal_embed(req: EmbedRequest):
    """供本地子进程调用的内部向量化高速接口"""
    if GLOBAL_EMBEDDER is None:
        raise HTTPException(status_code=500, detail="全局 Embedding 模型尚未加载完成")
    
    # 在主进程内极速计算向量并打包返回给 _core_rag 的 RemoteEmbedder
    embeddings = GLOBAL_EMBEDDER.encode(req.texts, show_progress_bar=False)
    return {"embeddings": embeddings.tolist()}
# =====================================================================

# --- 助手函数：Markdown 无序列表词库安全洗牌（解决生成套路化问题） ---
def shuffle_markdown_lists(filepath: str):
    """读取MD文件，仅打乱以 '- ' 或 '* ' 开头的列表项，保留标题和结构"""
    if not os.path.exists(filepath): return
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    out_lines = []
    current_list = []
    
    def flush_list():
        if current_list:
            random.shuffle(current_list)
            out_lines.extend(current_list)
            current_list.clear()

    for line in lines:
        if line.strip().startswith('- ') or line.strip().startswith('* '):
            current_list.append(line)
        else:
            flush_list()
            out_lines.append(line)
    flush_list()
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)


# --- 4. 基础 API 路由 ---
@router.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(CODE_DIR, "index.html"))

@router.post("/api/chat")
async def chat_stream(req: ChatRequest):
    client = AsyncOpenAI(api_key=req.api_key, base_url="https://api.deepseek.com")
    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    messages.extend(req.messages)

    async def generate():
        try:
            stream = await client.chat.completions.create(
                model=req.model,
                messages=messages,
                stream=True,
                temperature=req.temperature,
                top_p=req.top_p,
                stream_options={"include_usage": True} 
            )
            async for chunk in stream:
                # 处理正常文本流
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                
                # 提取 usage 并按前端格式返回以便前端正则拦截
                if getattr(chunk, 'usage', None) and chunk.usage:
                    yield f"__USAGE__:{chunk.usage.prompt_tokens},{chunk.usage.completion_tokens}__"
                    
        except Exception as e:
            yield f"\n\n[系统请求错误: {str(e)}]"

    return StreamingResponse(generate(), media_type="text/plain")

# --- 5. 小说工作台项目管理 API ---
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
    base_name = proj.name.strip()
    if not base_name.endswith("_style_imitation"):
        dir_name = f"{base_name}_style_imitation"
    else:
        dir_name = base_name
        
    target_proj_dir = os.path.join(PROJ_DIR, dir_name)
    
    # 1. 创建基础目录结构
    for folder in ["content", "character_profiles", "chapter_structures"]:
        os.makedirs(os.path.join(target_proj_dir, folder), exist_ok=True)

    # 2. 记录项目配置（锁定模式）
    config_path = os.path.join(target_proj_dir, "project_config.json")
    project_config = {
        "name": proj.name,
        "mode": proj.branch,  # 原创 | 同人 | 默认
        "reference_style": proj.reference_style,
        "created_at": datetime.now().isoformat()
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(project_config, f, ensure_ascii=False, indent=2)

    # 3. 根据模式执行文件初始化逻辑
    src_style_dir = os.path.join(STYLE_DIR, proj.reference_style) if proj.reference_style else None

    # === 同人模式 ===
    if proj.branch == "同人":
        if not src_style_dir or not os.path.exists(src_style_dir):
            return {"error": "同人模式必须选择有效的参考文风库"}
            
        # 全量拷贝文件
        for filename in ["features.md", "world_settings.md", "plot_outlines.md", "positive_words.md", "negative_words.md", "exclusive_vocab.md"]:
            src_file = os.path.join(src_style_dir, filename)
            if os.path.exists(src_file):
                shutil.copy2(src_file, os.path.join(target_proj_dir, filename))
        
        # 全量拷贝文件夹
        for folder in ["character_profiles", "hierarchical_rag_db"]:
            src_folder = os.path.join(src_style_dir, folder)
            if os.path.exists(src_folder):
                dst_folder = os.path.join(target_proj_dir, folder)
                if os.path.exists(dst_folder):
                    shutil.rmtree(dst_folder)
                shutil.copytree(src_folder, dst_folder)

    # === 原创模式 ===
    elif proj.branch == "原创":
        if not src_style_dir or not os.path.exists(src_style_dir):
            return {"error": "原创模式必须选择有效的参考文风库"}

        # 仅拷贝文风数据
        for filename in ["features.md", "positive_words.md", "negative_words.md"]:
            src_file = os.path.join(src_style_dir, filename)
            if os.path.exists(src_file):
                shutil.copy2(src_file, os.path.join(target_proj_dir, filename))
        
        # 强制生成空的设定文件（不拷贝原著设定）
        open(os.path.join(target_proj_dir, "world_settings.md"), 'w', encoding='utf-8').close()
        # character_profiles 已在前面创建为空目录
        # 不拷贝 hierarchical_rag_db

    # === 默认模式 ===
    else: # 默认模式或其他
        # 不执行任何拷贝，生成全量空白文件
        pass

    # 4. 兜底检测：确保核心文件存在（若未拷贝则生成空白）
    files_to_check = [
        "features.md", 
        "world_settings.md", 
        "positive_words.md",
        "negative_words.md"
    ]
    for filename in files_to_check:
        f_path = os.path.join(target_proj_dir, filename)
        if not os.path.exists(f_path):
            open(f_path, 'w', encoding='utf-8').close()
        
    with open(os.path.join(target_proj_dir, "content", "第一章.txt"), "w", encoding="utf-8") as f:
        f.write("这里是小说的开头...")
        
    return {"status": "success"}

@router.get("/api/projects/{proj_name}/chapters")
async def get_chapters(proj_name: str):
    content_dir = os.path.join(PROJ_DIR, proj_name, "content")
    if not os.path.exists(content_dir):
        return []
    return [f for f in os.listdir(content_dir) if f.endswith(".txt")]

@router.get("/api/projects/{proj_name}/characters")
async def get_characters(proj_name: str):
    char_dir = os.path.join(PROJ_DIR, proj_name, "character_profiles")
    if not os.path.exists(char_dir):
        return []
    return [os.path.splitext(f)[0] for f in os.listdir(char_dir) if f.endswith(".md")]

@router.post("/api/projects/{proj_name}/chapters/{chap_name}")
async def create_or_rename_chapter(proj_name: str, chap_name: str, new_name: str = None):
    content_dir = os.path.join(PROJ_DIR, proj_name, "content")
    if new_name:
        os.rename(os.path.join(content_dir, f"{chap_name}.txt"), os.path.join(content_dir, f"{new_name}.txt"))
    else:
        open(os.path.join(content_dir, f"{chap_name}.txt"), 'w', encoding='utf-8').close()
    return {"status": "success"}

@router.get("/api/projects/{proj_name}/chapters/{chap_name}/content")
async def get_chapter_content(proj_name: str, chap_name: str):
    filepath = os.path.join(PROJ_DIR, proj_name, "content", f"{chap_name}.txt")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    return {"content": ""}

@router.put("/api/projects/{proj_name}/chapters/{chap_name}/content")
async def update_chapter_content(proj_name: str, chap_name: str, update: ChapterUpdate):
    filepath = os.path.join(PROJ_DIR, proj_name, "content", f"{chap_name}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(update.content)
    return {"status": "success"}

@router.post("/api/projects/{proj_name}/append")
async def append_to_novel(proj_name: str, req: AppendContent):
    content_dir = os.path.join(PROJ_DIR, proj_name, "content")
    chapters = [f for f in os.listdir(content_dir) if f.endswith(".txt")]
    if not chapters:
        return {"error": "未找到章节文件"}
    target_file = os.path.join(content_dir, chapters[0])
    with open(target_file, "a", encoding="utf-8") as f:
        f.write("\n\n" + req.content)
    return {"status": "success"}

@router.get("/api/projects/{proj_name}/settings/{file_path:path}")
async def get_project_setting(proj_name: str, file_path: str):
    filepath = os.path.join(PROJ_DIR, proj_name, file_path)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    return {"content": "文件不存在或尚未生成，请检查工作流执行状态。"}

@router.put("/api/projects/{proj_name}/settings/{file_path:path}")
async def update_project_setting(proj_name: str, file_path: str, update: SettingUpdate):
    filepath = os.path.join(PROJ_DIR, proj_name, file_path)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(update.content)
    return {"status": "success"}

@router.get("/api/projects/{proj_name}/outlines")
async def get_outlines(proj_name: str):
    outline_dir = os.path.join(PROJ_DIR, proj_name, "chapter_structures")
    if not os.path.exists(outline_dir):
        return []
    return [f for f in os.listdir(outline_dir) if f.endswith(".md") or f.endswith(".json")]

# --- 6. 自动化工作流 API (后台执行调度) ---
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
        raise HTTPException(status_code=500, detail=str(e))

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
    target_path = os.path.join(REF_DIR, target_file) if not os.path.isabs(target_file) else target_file 
     
    if not os.path.exists(script_path): 
        return {"error": f"系统拦截：未找到物理脚本文件 [{script_path}]"} 
 
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
            "name": f"⏭️ [缓存跳过] {script_type} [{model}]: {target_name}", 
            "type": script_type, 
            "status": "success", 
            "created_at": datetime.now().isoformat(), 
            "end_time": datetime.now().isoformat(), 
            "ref_file": target_name, 
            "stdout": f"检测到本地已存在产物：{os.path.basename(target_output)}，自动跳过执行以节省 Token 与算力。", 
            "stderr": "", 
            "tokens": 0 
        } 
        return {"status": "started", "task_id": task_id, "message": "检测到缓存，已自动跳过"} 
    # ======================================================== 
 
    cmd = [sys.executable, script_path, "--target_file", target_path] 
    if project_name: 
        cmd.extend(["--project", project_name]) 
     
    if script_type in ["f1b", "f2b", "f3a", "f3b", "f3c", "f4a", "f5a", "f5b", "f6", "f7"]: 
        cmd.extend(["--model", model]) 
         
    if script_type == "f3c": 
        if not character: 
            return {"error": "执行 f3c 时必须传递 character 参数"} 
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
 
    asyncio.create_task(run_task_safely(task_id, cmd, x_api_key)) 
    return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: {script_name}"}

@router.post("/api/scripts/f4a_completion")
async def run_f4a_completion(req: SettingCompletionRequest, x_api_key: str = Header(None)):
    script_path = os.path.join(CODE_DIR, "scripts", "f4a_llm_setting_completion.py")
    if not os.path.exists(script_path):
        return {"error": f"未找到执行脚本 {script_path}"}
        
    json_string = json.dumps(req.form_data, ensure_ascii=False)
    target_path = os.path.join(REF_DIR, req.target_file) if not os.path.isabs(req.target_file) else req.target_file
    
    cmd = [
        sys.executable, script_path, 
        "--target_file", target_path,
        "--mode", req.mode,
        "--json_data", json_string,
        "--model", req.model
    ]
    if req.project_name:
        cmd.extend(["--project", req.project_name])
        
    task_id = str(uuid.uuid4())
    TASKS[task_id] = {
        "name": f"f4a [{req.model}]: {req.mode} - {os.path.basename(req.target_file)}",
        "type": "f4a",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "ref_file": os.path.basename(req.target_file)
    }
    
    asyncio.create_task(run_task_safely(task_id, cmd, x_api_key))
    return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f4a ({req.mode}模式)"}

@router.post("/api/scripts/f5a_outline")
async def run_f5a_outline(req: ChapterOutlineRequest, x_api_key: str = Header(None)):
    script_path = os.path.join(CODE_DIR, "scripts", "f5a_llm_chapter_outline.py")
    if not os.path.exists(script_path):
        return {"error": f"未找到执行脚本 {script_path}"}
        
    brief_json = json.dumps({"brief": req.chapter_brief}, ensure_ascii=False)
    cmd = [
        sys.executable, script_path, 
        "--project", req.project_name,
        "--chapter", req.chapter_name,
        "--brief", brief_json,
        "--model", req.model
    ]
    
    task_id = str(uuid.uuid4())
    TASKS[task_id] = {
        "name": f"f5a [{req.model}]: {req.project_name} - {req.chapter_name}",
        "type": "f5a",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "ref_file": req.project_name
    }

    asyncio.create_task(run_task_safely(task_id, cmd, x_api_key))
    return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: f5a 生成大纲"}

@router.post("/api/scripts/f5b_prompt_export")
async def export_f5b_prompt(req: NovelGenerationRequest):
    script_path = os.path.join(CODE_DIR, "scripts", "f5b_llm_novel_generation.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail=f"未找到执行脚本 {script_path}")
    
    project_config_path = os.path.join(PROJ_DIR, req.project_name, "project_config.json")
    branch_mode = "同人" 
    if os.path.exists(project_config_path):
        try:
            with open(project_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                branch_mode = config.get("mode", "同人")
        except:
            pass

    for dict_file in ["positive_words.md", "negative_words.md", "exclusive_vocab.md"]:
        dict_path = os.path.join(PROJ_DIR, req.project_name, dict_file)
        shuffle_markdown_lists(dict_path)

    cmd = [
        sys.executable, script_path, 
        "--project", req.project_name,
        "--chapter", req.chapter_name,
        "--model", req.model,
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
        raise HTTPException(status_code=500, detail=f"指令包组装导出失败: {stderr.decode('utf-8', errors='replace')}")
        
    return {"prompt": stdout.decode('utf-8', errors='replace')}

@router.post("/api/scripts/f5b_generate")
async def run_f5b_generate(req: NovelGenerationRequest, x_api_key: str = Header(None)):
    script_path = os.path.join(CODE_DIR, "scripts", "f5b_llm_novel_generation.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail=f"未找到执行脚本 {script_path}")
    
    project_config_path = os.path.join(PROJ_DIR, req.project_name, "project_config.json")
    branch_mode = "同人" 
    if os.path.exists(project_config_path):
        try:
            with open(project_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                branch_mode = config.get("mode", "同人")
        except:
            pass

    for dict_file in ["positive_words.md", "negative_words.md", "exclusive_vocab.md"]:
        dict_path = os.path.join(PROJ_DIR, req.project_name, dict_file)
        shuffle_markdown_lists(dict_path)

    cmd = [
        sys.executable, script_path, 
        "--project", req.project_name,
        "--chapter", req.chapter_name,
        "--model", req.model,
        "--branch", branch_mode
    ]

    async def stream_generator():
        env = os.environ.copy()
        if x_api_key:
            env["DEEPSEEK_API_KEY"] = x_api_key
            
        # 改用流式专属并发锁，防止由于后台切分等耗时任务占线导致 504 错误
        async with stream_semaphore:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                yield line.decode('utf-8')
            
            try:
                await asyncio.wait_for(process.wait(), timeout=1800.0)
            except asyncio.TimeoutError:
                process.kill()
                yield "\n\n[系统拦截：流式生成超时，进程已强制回收]"

    return StreamingResponse(stream_generator(), media_type="text/plain")