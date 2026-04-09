import os
import json
import shutil
from datetime import datetime

from fastapi import APIRouter, HTTPException

from .config import STYLE_DIR, PROJ_DIR
from .models import ProjectCreate, ChapterUpdate, AppendContent, SettingUpdate

# 【新增引入】：注入核心层提供的异步非阻塞安全 I/O 组件
from core._core_utils import async_smart_read_text, async_atomic_write, async_append_text

router = APIRouter()

# ==========================================
# 辅助函数与安全核心验证器
# ==========================================

def get_real_dir(proj_name: str):
    """【内部解析】：用来识别这是普通工程，还是文风库工程"""
    if proj_name.startswith("style@@"):
        return os.path.join(STYLE_DIR, proj_name.replace("style@@", ""))
    return os.path.join(PROJ_DIR, proj_name)

def get_validated_target_path(proj_name: str, file_path: str) -> str:
    """
    【双重安全核心验证器】：
    1. 防大本营劫持：严格校验 proj_name，确保 base_dir 被死死锁在合法沙箱内。
    2. 防目录穿越：严格校验 file_path，确保目标文件不越权。
    """
    # ================= 阶段一：锁定并校验大本营 =================
    raw_base_dir = get_real_dir(proj_name)
    safe_base_dir = os.path.realpath(os.path.abspath(raw_base_dir))
    
    # 获取理论上合法的根沙箱路径
    if proj_name.startswith("style@@"):
        expected_root = os.path.realpath(os.path.abspath(STYLE_DIR))
    else:
        expected_root = os.path.realpath(os.path.abspath(PROJ_DIR))
        
    norm_root = os.path.normcase(expected_root)
    norm_base = os.path.normcase(safe_base_dir)
    
    try:
        if os.path.commonpath([norm_root, norm_base]) != norm_root:
            raise HTTPException(status_code=403, detail="【系统拦截】：非法的项目名称越权访问！")
    except ValueError:
        raise HTTPException(status_code=403, detail="【系统拦截】：跨驱动器非法项目名称！")

    # ================= 阶段二：锁定并校验目标文件 =================
    target_path = os.path.realpath(os.path.abspath(os.path.join(safe_base_dir, file_path)))
    norm_target = os.path.normcase(target_path)
    
    try:
        if os.path.commonpath([norm_base, norm_target]) != norm_base:
            raise ValueError("检测到非法的目录穿越尝试")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=f"【系统拦截】：越权访问 ({str(e)})")
        
    return target_path


# ==========================================
# 小说工作台项目管理 API
# ==========================================

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
    base_dir = get_real_dir(proj_name)
    char_dir = os.path.join(base_dir, "character_profiles")
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
    # 此处假设不严格防跨越（原逻辑），但建议沿用通用逻辑
    filepath = os.path.join(PROJ_DIR, proj_name, "content", f"{chap_name}.txt")
    if os.path.exists(filepath):
        try:
            # 替换原生 open 为带有互斥锁的异步非阻塞读取
            content = await async_smart_read_text(filepath)
            return {"content": content}
        except OSError as e:
            raise HTTPException(status_code=500, detail="文件读取失败或被占用")
    return {"content": ""}

@router.put("/api/projects/{proj_name}/chapters/{chap_name}/content")
async def update_chapter_content(proj_name: str, chap_name: str, update: ChapterUpdate):
    filepath = os.path.join(PROJ_DIR, proj_name, "content", f"{chap_name}.txt")
    try:
        # 替换为带互斥锁的异步非阻塞原子写入
        await async_atomic_write(filepath, update.content, 'text')
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="保存章节内容失败")

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
        # 替换为带互斥锁的异步非阻塞追加写入
        await async_append_text(target_file, "\n\n" + req.content)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="追加内容失败")

# ==========================================
# 终极安全版设定读写接口 (重点升级部分)
# ==========================================

@router.get("/api/projects/{proj_name}/settings/{file_path:path}")
async def get_project_setting(proj_name: str, file_path: str):
    try:
        target_path = get_validated_target_path(proj_name, file_path)
    except HTTPException as e:
        return {"content": e.detail}
        
    if not os.path.isfile(target_path):
        return {"content": "文件不存在或尚未生成，请检查工作流执行状态。"}
        
    try:
        # 替换为带互斥锁的异步非阻塞读取
        content = await async_smart_read_text(target_path)
        return {"content": content}
    except Exception as e:
        return {"content": f"系统错误：文件读取异常。"}

@router.put("/api/projects/{proj_name}/settings/{file_path:path}")
async def update_project_setting(proj_name: str, file_path: str, update: SettingUpdate):
    try:
        target_path = get_validated_target_path(proj_name, file_path)
    except HTTPException as e:
        raise e
        
    if os.path.isdir(target_path):
        raise HTTPException(status_code=400, detail="【系统拦截】：目标路径已被文件夹占用，无法写入！")

    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        # 替换为带互斥锁的异步非阻塞原子写入
        await async_atomic_write(target_path, update.content, 'text')
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"系统错误：文件写入异常。")

# ==========================================
# 其他设定检索 API
# ==========================================

@router.get("/api/projects/{proj_name}/outlines")
async def get_outlines(proj_name: str):
    base_dir = get_real_dir(proj_name)
    outline_dir = os.path.join(base_dir, "chapter_structures")
    if not os.path.exists(outline_dir):
        return []
    return [f for f in os.listdir(outline_dir) if f.endswith(".md") or f.endswith(".json")]

@router.get("/api/projects/{proj_name}/phase1_status") 
async def check_phase1_status(proj_name: str): 
    """检测 f0-f3b (世界观) 是否已生成""" 
    base_dir = get_real_dir(proj_name) 
    target_file = os.path.join(base_dir, "world_settings.md" ) 
    is_done = os.path.exists(target_file) and os.path.getsize(target_file) > 50 
    return {"is_done" : is_done} 
 
@router.get("/api/projects/{proj_name}/prompts") 
async def get_prompts(proj_name: str): 
    """供知识库获取 prompt 指令列表""" 
    base_dir = get_real_dir(proj_name) 
    prompt_dir = os.path.join(base_dir, "chapter_specific_prompts" ) 
    if not os.path.exists(prompt_dir): 
        return [] 
    return [f for f in os.listdir(prompt_dir) if f.endswith(".txt" )]