import os
import json
import asyncio
import uuid
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
import uvicorn

# --- 1. 物理目录架构严格对齐文档 ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CODE_DIR = os.path.join(PROJECT_ROOT, "style_imitation_code")
REF_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")
DICT_DIR = os.path.join(PROJECT_ROOT, "dictionaries")
TEST_DIR = os.path.join(PROJECT_ROOT, "text_testing_code")

for directory in [CODE_DIR, REF_DIR, STYLE_DIR, PROJ_DIR, DICT_DIR, TEST_DIR]:
    os.makedirs(directory, exist_ok=True)

# --- 2. 系统全局并发控制 ---
task_semaphore = asyncio.Semaphore(1)
TASKS = {}

app = FastAPI(title="DeepSeek Ultimate Pro + Writer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. 数据模型定义 ---
class ChatRequest(BaseModel):
    api_key: str
    model: str
    messages: list
    system_prompt: str
    temperature: float
    top_p: float

class ProjectCreate(BaseModel):
    name: str

class ChapterUpdate(BaseModel):
    content: str

class AppendContent(BaseModel):
    content: str

class SettingUpdate(BaseModel):
    content: str

class SettingCompletionRequest(BaseModel):
    target_file: str
    mode: str 
    project_name: str = ""
    form_data: dict 
    model: str = "deepseek-chat"

class ChapterOutlineRequest(BaseModel):
    project_name: str
    chapter_name: str
    chapter_brief: str
    model: str = "deepseek-chat"

class NovelGenerationRequest(BaseModel):
    project_name: str
    chapter_name: str
    model: str = "deepseek-chat"
    branch: str = "同人创作"  # 新增：用于向 f5b 透传创作分支控制参数

# --- 4. 基础 API 路由 ---
@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(CODE_DIR, "index.html"))

@app.post("/api/chat")
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
                top_p=req.top_p
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"\n\n[系统请求错误: {str(e)}]"

    return StreamingResponse(generate(), media_type="text/plain")

# --- 5. 小说工作台项目管理 API ---
@app.get("/api/projects")
async def get_projects():
    return [f for f in os.listdir(PROJ_DIR) if os.path.isdir(os.path.join(PROJ_DIR, f))]

@app.post("/api/projects")
async def create_project(proj: ProjectCreate):
    base_name = proj.name.strip()
    if not base_name.endswith("_style_imitation"):
        dir_name = f"{base_name}_style_imitation"
    else:
        dir_name = base_name
        
    target_proj_dir = os.path.join(PROJ_DIR, dir_name)
    
    for folder in ["content", "character_profiles", "chapter_structures"]:
        os.makedirs(os.path.join(target_proj_dir, folder), exist_ok=True)
        
    files_to_create = [
        "features.md", 
        "world_settings.md", 
        "plot_outlines.md",
        "positive_words.md",
        "negative_words.md"
    ]
    for filename in files_to_create:
        open(os.path.join(target_proj_dir, filename), 'w', encoding='utf-8').close()
        
    with open(os.path.join(target_proj_dir, "content", "第一章.txt"), "w", encoding="utf-8") as f:
        f.write("这里是小说的开头...")
        
    return {"status": "success"}

@app.get("/api/projects/{proj_name}/chapters")
async def get_chapters(proj_name: str):
    content_dir = os.path.join(PROJ_DIR, proj_name, "content")
    if not os.path.exists(content_dir):
        return []
    return [f for f in os.listdir(content_dir) if f.endswith(".txt")]

@app.get("/api/projects/{proj_name}/characters")
async def get_characters(proj_name: str):
    char_dir = os.path.join(PROJ_DIR, proj_name, "character_profiles")
    if not os.path.exists(char_dir):
        return []
    return [os.path.splitext(f)[0] for f in os.listdir(char_dir) if f.endswith(".md")]

@app.post("/api/projects/{proj_name}/chapters/{chap_name}")
async def create_or_rename_chapter(proj_name: str, chap_name: str, new_name: str = None):
    content_dir = os.path.join(PROJ_DIR, proj_name, "content")
    if new_name:
        os.rename(os.path.join(content_dir, f"{chap_name}.txt"), os.path.join(content_dir, f"{new_name}.txt"))
    else:
        open(os.path.join(content_dir, f"{chap_name}.txt"), 'w', encoding='utf-8').close()
    return {"status": "success"}

@app.get("/api/projects/{proj_name}/chapters/{chap_name}/content")
async def get_chapter_content(proj_name: str, chap_name: str):
    filepath = os.path.join(PROJ_DIR, proj_name, "content", f"{chap_name}.txt")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    return {"content": ""}

@app.put("/api/projects/{proj_name}/chapters/{chap_name}/content")
async def update_chapter_content(proj_name: str, chap_name: str, update: ChapterUpdate):
    filepath = os.path.join(PROJ_DIR, proj_name, "content", f"{chap_name}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(update.content)
    return {"status": "success"}

@app.post("/api/projects/{proj_name}/append")
async def append_to_novel(proj_name: str, req: AppendContent):
    content_dir = os.path.join(PROJ_DIR, proj_name, "content")
    chapters = [f for f in os.listdir(content_dir) if f.endswith(".txt")]
    if not chapters:
        return {"error": "未找到章节文件"}
    target_file = os.path.join(content_dir, chapters[0])
    with open(target_file, "a", encoding="utf-8") as f:
        f.write("\n\n" + req.content)
    return {"status": "success"}

@app.get("/api/projects/{proj_name}/settings/{file_name}")
async def get_project_setting(proj_name: str, file_name: str):
    filepath = os.path.join(PROJ_DIR, proj_name, file_name)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    return {"content": "文件不存在或尚未生成，请检查工作流执行状态。"}

@app.put("/api/projects/{proj_name}/settings/{file_name}")
async def update_project_setting(proj_name: str, file_name: str, update: SettingUpdate):
    filepath = os.path.join(PROJ_DIR, proj_name, file_name)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(update.content)
    return {"status": "success"}

# --- 6. 自动化工作流 API (后台执行调度) ---
@app.get("/api/references")
async def get_references():
    return [f for f in os.listdir(REF_DIR) if os.path.isfile(os.path.join(REF_DIR, f))]

@app.get("/api/tasks")
async def list_tasks():
    sorted_tasks = sorted(TASKS.items(), key=lambda x: x[1].get('start_time', ''), reverse=True)
    return [{"id": k, **v} for k, v in sorted_tasks[:20]]

@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task

async def run_task_safely(task_id: str, cmd_list: list, api_key: str = None):
    TASKS[task_id]["status"] = "running"
    TASKS[task_id]["start_time"] = datetime.now().isoformat()
    
    env = os.environ.copy()
    if api_key:
        env["DEEPSEEK_API_KEY"] = api_key
        
    try:
        async with task_semaphore:
            process = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            stdout, stderr = await process.communicate()
            
            TASKS[task_id]["returncode"] = process.returncode
            TASKS[task_id]["stdout"] = stdout.decode('utf-8', errors='replace') if stdout else ""
            TASKS[task_id]["stderr"] = stderr.decode('utf-8', errors='replace') if stderr else ""
            
            if process.returncode == 0:
                TASKS[task_id]["status"] = "success"
            else:
                TASKS[task_id]["status"] = "failed"
                
    except Exception as e:
        TASKS[task_id]["status"] = "error"
        TASKS[task_id]["error"] = str(e)
    finally:
        TASKS[task_id]["end_time"] = datetime.now().isoformat()

@app.post("/api/scripts/{script_type}")
async def run_script(
    script_type: str, 
    target_file: str = "", 
    project_name: str = "", 
    character: str = "", 
    chapter_name: str = "", 
    model: str = "deepseek-chat",
    x_api_key: str = Header(None) 
):
    script_map = {
        "f1a": "f1a_local_text_stats.py",
        "f1b": "f1b_llm_style_feature.py",
        "f2a": "f2a_local_word_freq.py",
        "f2b": "f2b_llm_keyword_base.py",
        "f3a": "f3a_llm_exclusive_vocab.py",
        "f3b": "f3b_llm_worldview.py",
        "f3c": "f3c_llm_character.py",
        "f4":  "f4b_llm_plot_compression.py",
        "f6":  "f6_llm_plot_deduction.py",
        "f7":  "f7_llm_text_validation.py"
    }
    
    script_name = script_map.get(script_type)
    if not script_name:
        return {"error": f"未知的脚本类型或该模块需走专用路由: {script_type}"}
        
    script_path = os.path.join(CODE_DIR, script_name)
    target_path = os.path.join(REF_DIR, target_file) if not os.path.isabs(target_file) else target_file
    
    if not os.path.exists(script_path):
        return {"error": f"系统拦截：未找到物理脚本文件 [{script_name}]"}
        
    cmd = ["python", script_path, "--target_file", target_path]
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
    target_name = os.path.basename(target_file) if target_file else "无目标文件"
    if script_type == "f3c" and character:
        target_name += f" ({character})"
        
    TASKS[task_id] = {
        "name": f"{script_type} [{model}]: {target_name}",
        "type": script_type,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "ref_file": target_name
    }

    asyncio.create_task(run_task_safely(task_id, cmd, x_api_key))
    return {"status": "started", "task_id": task_id, "message": f"任务已加入执行队列: {script_name}"}

@app.post("/api/scripts/f4a_completion")
async def run_f4a_completion(req: SettingCompletionRequest, x_api_key: str = Header(None)):
    script_path = os.path.join(CODE_DIR, "f4a_llm_setting_completion.py")
    if not os.path.exists(script_path):
        return {"error": "未找到执行脚本 f4a_llm_setting_completion.py"}
        
    json_string = json.dumps(req.form_data, ensure_ascii=False)
    target_path = os.path.join(REF_DIR, req.target_file) if not os.path.isabs(req.target_file) else req.target_file
    
    cmd = [
        "python", script_path, 
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

@app.post("/api/scripts/f5a_outline")
async def run_f5a_outline(req: ChapterOutlineRequest, x_api_key: str = Header(None)):
    script_path = os.path.join(CODE_DIR, "f5a_llm_chapter_outline.py")
    if not os.path.exists(script_path):
        return {"error": "未找到执行脚本 f5a_llm_chapter_outline.py"}
        
    brief_json = json.dumps({"brief": req.chapter_brief}, ensure_ascii=False)
    cmd = [
        "python", script_path, 
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

@app.post("/api/scripts/f5b_generate")
async def run_f5b_generate(req: NovelGenerationRequest, x_api_key: str = Header(None)):
    script_path = os.path.join(CODE_DIR, "f5b_llm_novel_generation.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="未找到执行脚本 f5b_llm_novel_generation.py")
        
    cmd = [
        "python", script_path, 
        "--project", req.project_name,
        "--chapter", req.chapter_name,
        "--model", req.model,
        "--branch", req.branch
    ]

    async def stream_generator():
        env = os.environ.copy()
        if x_api_key:
            env["DEEPSEEK_API_KEY"] = x_api_key
            
        async with task_semaphore:
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
            await process.wait()

    return StreamingResponse(stream_generator(), media_type="text/plain")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)