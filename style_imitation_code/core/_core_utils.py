import re
import sys
import os
import tempfile
import uuid
import shutil
import glob
import json
import asyncio

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
    # 必须剥离原始 basename，防止恶意文件名被传入 CLI
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
    
    # 识别到票据前缀，自动劫持并重定向至沙箱路径
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
    """
    带高水位线保护的自然段动态缓冲流式读取器。
    
    :param chunk_size: 每次物理 I/O 读取的字节数
    :param high_water_mark: 内存缓冲区高水位警戒线（默认 1MB），防止无换行长文本导致 OOM
    """
    basename = os.path.basename(file_path)
    if basename.startswith("TKT-"):
        try:
            file_path = resolve_sandbox_ticket(basename)
        except Exception as e:
            raise RuntimeError(f"票据解析拦截: {mask_sensitive_info(str(e))}")

    encodings_to_try = ['utf-8', 'gb18030', 'utf-16']
    target_encoding = None

    # 嗅探有效编码
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
                
                # 内存高水位线强制截断
                if len(buffer) > high_water_mark:
                    print(f"[WARN] 触发内存高水位告警 ({high_water_mark} bytes)，执行强制截断以防 OOM。")
                    yield buffer
                    buffer = ""
                    continue

                # 动态寻找最后一次换行符的物理边界
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

class AsyncFileLockManager: 
    """全局单例：文件级细粒度异步锁状态机""" 
    _locks = {} 
    _ref_counts = {} 
    _dict_lock = asyncio.Lock() 

class async_file_lock: 
    """ 
    生产级文件读写异步互斥锁 (Context Manager)。 
    利用引用计数实现内存确定性释放，避免高并发下字典无限膨胀。 
    """ 
    def __init__(self, file_path: str): 
        if not file_path: 
            raise ValueError("系统拦截：文件路径不能为空" ) 
        # 绝对路径标准化，防止相同文件的不同路径表达绕过锁机制 
        self.norm_path = os.path.normcase(os.path.realpath(os.path.abspath(file_path))) 

    async def __aenter__(self): 
        async with AsyncFileLockManager._dict_lock: 
            if self.norm_path not in AsyncFileLockManager._locks: 
                AsyncFileLockManager._locks[self.norm_path] = asyncio.Lock() 
                AsyncFileLockManager._ref_counts[self.norm_path] = 0 
            AsyncFileLockManager._ref_counts[self.norm_path] += 1 
            self.lock = AsyncFileLockManager._locks[self.norm_path] 
        
        # 挂起当前协程，等待获取该文件的独占操作权 
        await self.lock.acquire() 
        return self 

    async def __aexit__(self, exc_type, exc_val, exc_tb): 
        self.lock.release() 
        async with AsyncFileLockManager._dict_lock: 
            AsyncFileLockManager._ref_counts[self.norm_path] -= 1 
            # 引用计数归零时，主动销毁锁对象，释放内存 
            if AsyncFileLockManager._ref_counts[self.norm_path] <= 0 : 
                AsyncFileLockManager._locks.pop(self.norm_path, None ) 
                AsyncFileLockManager._ref_counts.pop(self.norm_path, None ) 

async def async_smart_read_text(file_path: str, max_len: int = None) -> str: 
    """异步非阻塞安全读取：自带文件粒度并发锁与线程池卸载""" 
    async with async_file_lock(file_path): 
        return await asyncio.to_thread(smart_read_text, file_path, max_len) 

async def async_atomic_write(target_path: str, data, data_type: str = 'text') -> bool: 
    """异步非阻塞原子写入：自带文件粒度并发锁与线程池卸载""" 
    async with async_file_lock(target_path): 
        return await asyncio.to_thread(atomic_write, target_path, data, data_type) 

async def async_append_text(target_path: str, content: str) -> bool: 
    """异步非阻塞追加写入：自带文件粒度并发锁与线程池卸载""" 
    def _append(): 
        with open(target_path, "a", encoding="utf-8") as f: 
            f.write(content) 
        return True 
        
    async with async_file_lock(target_path): 
        return await asyncio.to_thread(_append)