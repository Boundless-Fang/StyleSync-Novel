import os
# 【关键配置】：在导入模型库之前，强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
import json
import asyncio
import uuid
import re
import random
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Header, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
import uvicorn
import sys
import io
import shutil

# 强制重定向标准输出，允许 Windows 控制台处理 Emoji 字符
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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
    branch: str = "原创"  # 选项：原创 | 同人 | 默认
    reference_style: str = ""

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
    # branch 参数已废弃，后端将自动从 project_config.json 读取

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
                top_p=req.top_p,
                stream_options={"include_usage": True} # 【新增】：开启流式 Token 统计选项
            )
            async for chunk in stream:
                # 处理正常文本流
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                
                # 【新增】：提取 usage 并按前端格式返回以便前端正则拦截
                if getattr(chunk, 'usage', None) and chunk.usage:
                    yield f"__USAGE__:{chunk.usage.prompt_tokens},{chunk.usage.completion_tokens}__"
                    
        except Exception as e:
            yield f"\n\n[系统请求错误: {str(e)}]"

    return StreamingResponse(generate(), media_type="text/plain")

# --- 5. 小说工作台项目管理 API ---
@app.get("/api/projects")
async def get_projects():
    return [f for f in os.listdir(PROJ_DIR) if os.path.isdir(os.path.join(PROJ_DIR, f))]

@app.get("/api/styles")
async def get_styles():
    if not os.path.exists(STYLE_DIR):
        return []
    return [f for f in os.listdir(STYLE_DIR) if os.path.isdir(os.path.join(STYLE_DIR, f))]

@app.post("/api/projects")
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

@app.get("/api/projects/{proj_name}/settings/{file_path:path}")
async def get_project_setting(proj_name: str, file_path: str):
    filepath = os.path.join(PROJ_DIR, proj_name, file_path)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    return {"content": "文件不存在或尚未生成，请检查工作流执行状态。"}

@app.put("/api/projects/{proj_name}/settings/{file_path:path}")
async def update_project_setting(proj_name: str, file_path: str, update: SettingUpdate):
    filepath = os.path.join(PROJ_DIR, proj_name, file_path)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(update.content)
    return {"status": "success"}

@app.get("/api/projects/{proj_name}/outlines")
async def get_outlines(proj_name: str):
    outline_dir = os.path.join(PROJ_DIR, proj_name, "chapter_structures")
    if not os.path.exists(outline_dir):
        return []
    return [f for f in os.listdir(outline_dir) if f.endswith(".md") or f.endswith(".json")]

# --- 6. 自动化工作流 API (后台执行调度) ---
@app.get("/api/references")
async def get_references():
    return [f for f in os.listdir(REF_DIR) if os.path.isfile(os.path.join(REF_DIR, f))]

# 【新增】：接收前端上传的 txt/md 文件落盘至 reference_novels
@app.post("/api/references/upload")
async def upload_reference(file: UploadFile = File(...)):
    try:
        file_path = os.path.join(REF_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"status": "success", "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
            
            try:
                # 修复4：缺乏并发任务的状态保护。设置最大30分钟的超时限制，超时则斩杀进程
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=1800.0)
                
                stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
                stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""
                
                TASKS[task_id]["returncode"] = process.returncode
                TASKS[task_id]["stdout"] = stdout_str
                TASKS[task_id]["stderr"] = stderr_str
                
                # 修复1：任务栏 Token 统计失效。解析 stdout 提取模型调用的消耗统计并绑定给前端展示
                # 常见输出捕获: "Total Tokens: 123" / "总消耗 Token=123" / "tokens : 123"
                token_matches = re.findall(r'(?:[Tt]okens?|消耗)[:=：\s]*(\d+)', stdout_str)
                if token_matches:
                    TASKS[task_id]["tokens"] = int(token_matches[-1]) # 取最后一个累计值
                else:
                    TASKS[task_id]["tokens"] = 0
                
                if process.returncode == 0:
                    TASKS[task_id]["status"] = "success"
                else:
                    TASKS[task_id]["status"] = "failed"
                    
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()  # 清除残留流
                TASKS[task_id]["status"] = "failed"
                TASKS[task_id]["error"] = "超时异常：任务执行超过设定时间 (30分钟)，已被后台强制终止拦截以防止僵尸进程。"
                TASKS[task_id]["tokens"] = 0
                
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
    force: bool = False, # 👈 新增：是否强制重跑参数 
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
    # 【新增功能】：一键流水线 断点检索与跳过机制 
    # ======================================================== 
    # 根据 target_file 解析出小说名对应的输出目录 
    novel_name = os.path.splitext(os.path.basename(target_file))[0] if target_file else "" 
    style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation") 
     
    # 定义每个脚本执行成功后对应的“核心产物文件” 
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
     
    # 检查产物是否存在且不为空（大于 10 bytes 防空壳文件） 
    target_output = check_file_map.get(script_type) 
    # 👈 新增：如果 force=True，则无视这段缓存跳过逻辑 
    if not force and target_output and os.path.exists(target_output) and os.path.getsize(target_output) > 10: 
        task_id = str(uuid.uuid4()) 
        # 直接伪造一个“秒完成”的成功任务，返回给前端 
        TASKS[task_id] = { 
            "name": f"⏭️ [缓存跳过] {script_type} [{model}]: {target_name}", 
            "type": script_type, 
            "status": "success",  # 直接标记为成功 
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

@app.post("/api/scripts/f4a_completion")
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

@app.post("/api/scripts/f5a_outline")
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

@app.post("/api/scripts/f5b_prompt_export")
async def export_f5b_prompt(req: NovelGenerationRequest):
    """
    修复2：提供单纯组装不执行推理的接口导出最终合并 Prompt (要求底层 f5b 脚本接收 --export_prompt_only 标志)
    """
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

    # 修复3：在获取组装提示词前，打乱词库数据
    for dict_file in ["positive_words.md", "negative_words.md", "exclusive_vocab.md"]:
        dict_path = os.path.join(PROJ_DIR, req.project_name, dict_file)
        shuffle_markdown_lists(dict_path)

    cmd = [
        sys.executable, script_path, 
        "--project", req.project_name,
        "--chapter", req.chapter_name,
        "--model", req.model,
        "--branch", branch_mode,
        "--export_prompt_only"  # 传递专用标记要求底层仅返回提示词打印
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

@app.post("/api/scripts/f5b_generate")
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

    # 修复3：在每次执行正文生成(f5b)前，动态打乱该项目的词汇库内部顺序，防止大模型风格套路化
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
            
            # 这里的等待加入了超时机制以保障数据流不会僵死
            try:
                await asyncio.wait_for(process.wait(), timeout=1800.0)
            except asyncio.TimeoutError:
                process.kill()
                yield "\n\n[系统拦截：流式生成超时，进程已强制回收]"

    return StreamingResponse(stream_generator(), media_type="text/plain")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)