import re
import sys
import os
import tempfile
import uuid
import shutil
import glob
import json

# 动态获取系统临时目录构建独立沙箱
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX_DIR = os.path.join(tempfile.gettempdir(), "style_sync_sandbox")
os.makedirs(SANDBOX_DIR, exist_ok=True)

def mask_sensitive_info(error_msg: str) -> str:
    """异常拦截器：脱敏报错堆栈中的服务器真实绝对路径。"""
    msg = str(error_msg)
    msg = msg.replace(PROJECT_ROOT, "[SERVER_WORKSPACE]")
    msg = msg.replace(SANDBOX_DIR, "[SECURE_SANDBOX]")
    # 泛化兜底：屏蔽常见的盘符绝对路径暴露
    msg = re.sub(r'[A-Za-z]:\\[^\s"\'<>]+', '[LOCAL_PATH]', msg)
    msg = re.sub(r'/(?:tmp|usr|opt|var|home|etc)/[^\s"\'<>]+', '[LOCAL_PATH]', msg)
    return msg

def validate_safe_param(param: str) -> str:
    """白名单校验外部参数，防 Shell/Argparse 注入"""
    if not param: 
        return param
    param = str(param).strip()
    if param.startswith("-"): 
        raise ValueError("安全拦截：参数禁止以连字符开头")
    # 仅允许中英数、下划线、减号、括号、空格、逗号与点号
    if not re.match(r'^[\w\-\s\u4e00-\u9fa5\(\)（），,\.]+$', param):
        raise ValueError("安全拦截：参数包含非法特殊字符")
    return param

def create_sandbox_ticket(source_file_path: str) -> str:
    """生成一次性安全票据，并将源文件安全投递至沙箱。"""
    if not source_file_path or not os.path.exists(source_file_path):
        return ""
    
    ticket_id = f"TKT-{uuid.uuid4().hex}"
    # 【安全修正】：必须剥离原始 basename，防止恶意文件名被传入 CLI
    ext = os.path.splitext(source_file_path)[1] or ".txt"
    sandbox_path = os.path.join(SANDBOX_DIR, f"{ticket_id}{ext}")
    
    try:
        os.link(source_file_path, sandbox_path)
    except OSError:
        shutil.copy2(source_file_path, sandbox_path)
        
    return ticket_id

def resolve_sandbox_ticket(ticket_id: str) -> str:
    """逆向解析票据，仅允许检索限定在沙箱内部的文件。"""
    # 剔除可能附带的扩展名，仅提取核心票据ID
    ticket_base = os.path.splitext(os.path.basename(ticket_id))[0]
    
    if not ticket_base.startswith("TKT-") or not re.match(r'^TKT-[a-f0-9]{32}$', ticket_base):
        raise ValueError("非法的票据标识符")
        
    matches = glob.glob(os.path.join(SANDBOX_DIR, f"{ticket_base}.*"))
    if not matches:
        raise FileNotFoundError("票据生命周期已结束或文件不存在")
        
    safe_target = os.path.normcase(os.path.realpath(os.path.abspath(matches[0])))
    safe_base = os.path.normcase(os.path.realpath(os.path.abspath(SANDBOX_DIR)))
    if os.path.commonpath([safe_base, safe_target]) != safe_base:
        raise PermissionError("沙箱越权读取拦截")
        
    return safe_target

def cleanup_sandbox_ticket(ticket_id: str):
    """清理指定票据在沙箱中产生的所有物理碎片。"""
    if not ticket_id: 
        return
    ticket_base = os.path.splitext(os.path.basename(ticket_id))[0]
    if not ticket_base.startswith("TKT-"): 
        return
        
    matches = glob.glob(os.path.join(SANDBOX_DIR, f"{ticket_base}.*"))
    for match in matches:
        try:
            os.remove(match)
        except OSError:
            pass

def smart_read_text(file_path, max_len=None):
    """智能读取中文小说，防止崩溃。已整合底层无感沙箱解析机制。"""
    
    # 【无缝挂载】：识别到票据前缀，自动劫持并重定向至沙箱路径
    basename = os.path.basename(file_path)
    if basename.startswith("TKT-"):
        try:
            file_path = resolve_sandbox_ticket(basename)
        except Exception as e:
            raise RuntimeError(f"票据解析拦截: {mask_sensitive_info(str(e))}")

    encodings_to_try = ['utf-8', 'gb18030', 'utf-16']
    text = None
    
    for enc in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                text = f.read(max_len) if max_len else f.read()
            return text
        except UnicodeDecodeError:
            continue
            
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read(max_len) if max_len else f.read()
            
        sample = text[:1000]
        chinese_chars = re.findall(r'[\u4e00-\u9fa5，。！？“”]', sample)
        
        if len(sample) > 100 and (len(chinese_chars) / len(sample)) < 0.2:
            raise Exception("文件读取后汉字密度过低，判定为乱码或格式损坏，已拦截。")
            
        print("[WARN] 警告：文件存在非法字节，已强行修复并清理乱码碎片。")
        return text
        
    except Exception as e:
        error_msg = f"文件解析彻底失败: {mask_sensitive_info(str(e))}"
        print(f"[ERROR] {error_msg}")
        raise RuntimeError(error_msg)

def resolve_sandbox_path(base_dir: str, user_input_path: str, allowed_extensions=('.txt', '.md')) -> str: 
    """基础目录守卫：将外部输入安全的限制在指定根目录内。""" 
    if not user_input_path: 
        raise ValueError("输入路径不能为空") 

    safe_base = os.path.normcase(os.path.realpath(os.path.abspath(base_dir))) 
    raw_target = os.path.join(safe_base, user_input_path) 
    safe_target = os.path.normcase(os.path.realpath(os.path.abspath(raw_target))) 
    
    if os.path.commonpath([safe_base, safe_target]) != safe_base: 
        raise PermissionError("【系统拦截】：检测到越权路径访问尝试！") 
        
    if os.path.isdir(safe_target): 
        raise IsADirectoryError("【系统拦截】：目标路径为文件夹，拒绝读取！") 
        
    if allowed_extensions and not safe_target.endswith(allowed_extensions): 
        raise ValueError(f"【系统拦截】：不支持的文件格式，仅允许 {allowed_extensions}") 
        
    return safe_target

def atomic_write(target_path: str, data, data_type: str = 'text'): 
    """ 
    全局通用原子写入器 (Atomic Writer) 
    防止进程被强杀、超时或断电导致的目标文件损坏与残缺。 
    
    :param target_path: 最终需要保存的绝对路径 
    :param data: 需要写入的数据 (字符串 / 字典或列表 / FAISS Index 对象) 
    :param data_type: 数据格式，支持 'text', 'json', 'faiss' 
    """ 
    dirname = os.path.dirname(target_path) 
    if dirname: 
        os.makedirs(dirname, exist_ok=True) 
        
    # 1. 临时态隔离：生成带 UUID 的独立临时文件 
    temp_path = f"{target_path}.{uuid.uuid4().hex}.tmp" 
    
    try: 
        # 2. 针对不同类型执行写入 
        if data_type == 'json': 
            with open(temp_path, 'w', encoding='utf-8') as f: 
                json.dump(data, f, ensure_ascii=False, indent=2) 
        elif data_type == 'faiss': 
            import faiss 
            faiss.write_index(data, temp_path) 
        else:  # 默认为纯文本 'text' 
            with open(temp_path, 'w', encoding='utf-8') as f: 
                f.write(str(data)) 
                
        # 3. 操作系统级原子重命名覆盖 (瞬间替换，绝对安全) 
        os.replace(temp_path, target_path) 
        return True 
        
    except Exception as e: 
        # 4. 事务回滚：发生异常时主动清理产生的物理碎片 
        if os.path.exists(temp_path): 
            try: 
                os.remove(temp_path) 
            except OSError: 
                pass 
        raise RuntimeError(f"原子写入事务失败，已回滚: {str(e)}")