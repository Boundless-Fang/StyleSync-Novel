import re
import sys
import os
import tempfile
import uuid
import shutil
import glob
import json
import asyncio
import time      
import random    

# 动态获取系统临时目录构建独立沙箱
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX_DIR = os.path.join(tempfile.gettempdir(), "style_sync_sandbox")
os.makedirs(SANDBOX_DIR, exist_ok=True)

def mask_sensitive_info(error_msg: str) -> str:
    """异常拦截器：脱敏报错堆栈中的服务器真实绝对路径与高危鉴权凭证。"""
    msg = str(error_msg)
    
    # 1. 物理环境脱敏：拦截绝对工作区与沙箱路径
    msg = msg.replace(PROJECT_ROOT, "[SERVER_WORKSPACE]")
    msg = msg.replace(SANDBOX_DIR, "[SECURE_SANDBOX]")
    
    # 2. 泛化兜底：屏蔽常见的盘符绝对路径暴露
    msg = re.sub(r'[A-Za-z]:\\[^\s"\'<>]+', '[LOCAL_PATH]', msg)
    msg = re.sub(r'/(?:tmp|usr|opt|var|home|etc)/[^\s"\'<>]+', '[LOCAL_PATH]', msg)
    
    # 3. 鉴权资产脱敏：基于高危特征库的正则深度清洗
    msg = re.sub(r'sk-[a-zA-Z0-9]{20,}', '[REDACTED_API_KEY]', msg)
    msg = re.sub(r'Bearer\s+[a-zA-Z0-9\-\.\_]{20,}', 'Bearer [REDACTED_TOKEN]', msg)
    
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
    ext = os.path.splitext(source_file_path)[1] or ".txt"
    sandbox_path = os.path.join(SANDBOX_DIR, f"{ticket_id}{ext}")
    
    try:
        os.link(source_file_path, sandbox_path)
    except OSError:
        shutil.copy2(source_file_path, sandbox_path)
        
    return ticket_id

def resolve_sandbox_ticket(ticket_id: str) -> str:
    """逆向解析票据，仅允许检索限定在沙箱内部的文件。"""
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
    """智能读取中文小说，防止崩溃。"""
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

def smart_yield_text(file_path: str, chunk_size: int = 8192, high_water_mark: int = 1048576):
    """带高水位线保护的自然段动态缓冲流式读取器。"""
    basename = os.path.basename(file_path)
    if basename.startswith("TKT-"):
        try:
            file_path = resolve_sandbox_ticket(basename)
        except Exception as e:
            raise RuntimeError(f"票据解析拦截: {mask_sensitive_info(str(e))}")

    encodings_to_try = ['utf-8', 'gb18030', 'utf-16']
    target_encoding = None

    for enc in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                f.read(100)
            target_encoding = enc
            break
        except UnicodeDecodeError:
            continue
            
    if not target_encoding:
        target_encoding = 'utf-8'

    buffer = ""
    try:
        with open(file_path, 'r', encoding=target_encoding, errors='ignore') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    if buffer:
                        yield buffer
                    break

                buffer += chunk
                
                if len(buffer) > high_water_mark:
                    print(f"[WARN] 触发内存高水位告警 ({high_water_mark} bytes)，执行强制截断以防 OOM。")
                    yield buffer
                    buffer = ""
                    continue

                last_newline_idx = buffer.rfind('\n')
                if last_newline_idx != -1:
                    yield buffer[:last_newline_idx + 1]
                    buffer = buffer[last_newline_idx + 1:]
                    
    except Exception as e:
        error_msg = f"流式文件解析异常: {mask_sensitive_info(str(e))}"
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
    全局通用原子写入器 (Atomic Writer) - 重构版
    彻底修复 Windows 独占锁导致的不可逆数据丢失缺陷。
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
        else:  # 'text'
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(str(data))
                
        # 3. 延长的防惊群退避机制
        max_retries = 10     # 次数翻倍
        base_delay = 0.2     # 基础延迟翻4倍
        max_delay = 3.0      # 单次休眠封顶 3 秒
        
        for attempt in range(max_retries):
            try:
                os.replace(temp_path, target_path)
                return True
            except PermissionError as e:
                if attempt < max_retries - 1:
                    # 带封顶的温和指数退避 + 随机抖动
                    sleep_time = min(max_delay, base_delay * (1.5 ** attempt)) + random.uniform(0, 0.1)
                    time.sleep(sleep_time)
                    continue
                else:
                    # 4. 核心避险：超越重试上限后，保留孤儿临时文件，严禁删除数据！
                    backup_path = f"{target_path}.backup-{int(time.time())}.txt"
                    try:
                        os.replace(temp_path, backup_path)
                        raise RuntimeError(f"目标文件被其它软件死死锁定，无法覆写。为防数据丢失，已为您生成紧急备份: {backup_path}")
                    except OSError:
                        raise RuntimeError(f"文件锁定且重命名失败。AI 辛苦生成的数据已保留在临时文件中: {temp_path}")
                    
    except Exception as e:
        # 5. 事务回滚：只有在非锁死错误（如磁盘满、JSON序列化错误）时，才清理产生的物理碎片
        if not isinstance(e, RuntimeError) or ("紧急备份" not in str(e) and "临时文件保留" not in str(e)):
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        raise RuntimeError(f"原子写入事务失败，详情: {str(e)}")

class AsyncFileLockManager:
    """全局单例：文件级细粒度异步锁状态机（常驻内存池）"""
    _locks = {}
    _dict_lock = asyncio.Lock()

class async_file_lock:
    """生产级文件读写异步互斥锁"""
    def __init__(self, file_path: str):
        if not file_path:
            raise ValueError("系统拦截：文件路径不能为空")
        self.norm_path = os.path.normcase(os.path.realpath(os.path.abspath(file_path)))

    async def __aenter__(self):
        async with AsyncFileLockManager._dict_lock:
            if self.norm_path not in AsyncFileLockManager._locks:
                AsyncFileLockManager._locks[self.norm_path] = asyncio.Lock()
            self.lock = AsyncFileLockManager._locks[self.norm_path]
        
        await self.lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()

async def async_smart_read_text(file_path: str, max_len: int = None) -> str:
    async with async_file_lock(file_path):
        return await asyncio.to_thread(smart_read_text, file_path, max_len)

async def async_atomic_write(target_path: str, data, data_type: str = 'text') -> bool:
    async with async_file_lock(target_path):
        return await asyncio.to_thread(atomic_write, target_path, data, data_type)

async def async_append_text(target_path: str, content: str) -> bool:
    def _append():
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(content)
        return True
        
    async with async_file_lock(target_path):
        return await asyncio.to_thread(_append)