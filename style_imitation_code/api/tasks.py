import os
import json
import asyncio
import re
import subprocess
from datetime import datetime
from .config import PROJ_DIR

# 引入核心层的原子写与安全模块
from core._core_utils import atomic_write, mask_sensitive_info

# 系统全局并发控制与防护
background_semaphore = asyncio.Semaphore(1)
stream_semaphore = asyncio.Semaphore(3)

# 核心任务字典与持久化配置
TASKS = {}
TASKS_DB_PATH = os.path.join(PROJ_DIR, "system_tasks_db.json")
MAX_RETAINED_TASKS = 50

# I/O 互斥锁，防止并发写盘损坏文件
db_save_lock = asyncio.Lock()
# 内存状态互斥锁，严格保护 TASKS 字典的读写原子性
tasks_state_lock = asyncio.Lock()

def load_tasks_safe():
    """防线四：启动时的防尸变机制 (同步执行，无需加锁)"""
    global TASKS
    if os.path.exists(TASKS_DB_PATH):
        try:
            with open(TASKS_DB_PATH, 'r', encoding='utf-8') as f:
                loaded_tasks = json.load(f)
            for t_id, t_info in loaded_tasks.items():
                if t_info.get("status") in ["running", "pending"]:
                    t_info["status"] = "failed"
                    t_info["error"] = "系统拦截：检测到服务端曾发生重启或意外崩溃，该任务物理进程已丢失。"
            TASKS.update(loaded_tasks)
        except OSError as e:
            print(f"[WARN] 历史任务数据库加载失败，文件系统读取异常: {mask_sensitive_info(str(e))}")
        except json.JSONDecodeError as e:
            print(f"[WARN] 历史任务数据库加载失败，JSON格式已损坏: {str(e)}")

async def add_task_safe(task_id: str, task_info: dict):
    """提供给外部路由的安全写入接口"""
    async with tasks_state_lock:
        TASKS[task_id] = task_info

async def save_and_prune_tasks_async():
    """防线升级：缩减临界区，分离状态快照与无锁落盘"""
    async with db_save_lock:
        async with tasks_state_lock:
            finished_tasks = {
                k: v for k, v in TASKS.items()
                if v.get("status") not in ["running", "pending"]
            }
            
            if len(finished_tasks) > MAX_RETAINED_TASKS:
                sorted_keys = sorted(
                    finished_tasks.keys(),
                    key=lambda k: finished_tasks[k].get('created_at', ''),
                    reverse=True
                )
                keys_to_delete = sorted_keys[MAX_RETAINED_TASKS:]
                for k in keys_to_delete:
                    TASKS.pop(k, None)

            snapshot = {k: v.copy() for k, v in TASKS.items()}

        try:
            await asyncio.to_thread(atomic_write, TASKS_DB_PATH, snapshot, 'json')
        except (RuntimeError, OSError) as e:
            print(f"[ERROR] 任务状态落盘失败: {mask_sensitive_info(str(e))}")

async def run_task_safely(task_id: str, cmd_list: list, api_key: str = None):
    """
    核心异步调度器 (已重构)：
    1. 彻底废除外部 Thread 监控，消除 PID 错杀风险与线程资源泄露。
    2. 利用 asyncio.wait_for 实现原生句柄级的超时销毁。
    """
    async with tasks_state_lock:
        if task_id in TASKS:
            TASKS[task_id]["status"] = "running"
            TASKS[task_id]["start_time"] = datetime.now().isoformat()
            TASKS[task_id]["stdout"] = ""
            TASKS[task_id]["stderr"] = ""
            TASKS[task_id]["tokens"] = 0
    
    asyncio.create_task(save_and_prune_tasks_async())
    
    env = os.environ.copy()
    if api_key:
        env["DEEPSEEK_API_KEY"] = api_key
    env["PYTHONIOENCODING"] = "utf-8"
        
    try:
        async with background_semaphore:
            process = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            async def pipe_reader(stream, key):
                buffer = []
                flush_counter = 0
                while True:
                    try:
                        line = await stream.readline()
                        if not line: break
                    except (asyncio.LimitOverrunError, OSError):
                        break
                    
                    try:
                        decoded_line = line.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded_line = line.decode('gbk', errors='replace')
                    
                    buffer.append(decoded_line)
                    flush_counter += 1
                    
                    if key == "stdout":
                        token_matches = re.findall(r'(?:[Tt]okens?|消耗)[:=：\s]*(\d+)', decoded_line)
                        if token_matches:
                            async with tasks_state_lock:
                                if task_id in TASKS:
                                    TASKS[task_id]["tokens"] = int(token_matches[-1])

                    if flush_counter >= 50:
                        async with tasks_state_lock:
                            if task_id in TASKS:
                                TASKS[task_id][key] += "".join(buffer)
                        buffer.clear()
                        flush_counter = 0

                if buffer:
                    async with tasks_state_lock:
                        if task_id in TASKS:
                            TASKS[task_id][key] += "".join(buffer)

            try:
                # 设定 1800 秒强制超时，通过原生 Process 对象管理生命周期
                await asyncio.wait_for(
                    asyncio.gather(
                        pipe_reader(process.stdout, "stdout"),
                        pipe_reader(process.stderr, "stderr"),
                        process.wait()
                    ),
                    timeout=1800.0
                )
                
                async with tasks_state_lock:
                    if task_id in TASKS:
                        TASKS[task_id]["returncode"] = process.returncode
                        TASKS[task_id]["status"] = "success" if process.returncode == 0 else "failed"
                                
            except asyncio.TimeoutError: 
                # 方案一核心逻辑：直接操作进程句柄，而非盲杀 PID
                try: 
                    process.kill() # 强制销毁
                    await process.wait() # 确保句柄释放
                except OSError: 
                    pass
                    
                async with tasks_state_lock:
                    if task_id in TASKS:
                        TASKS[task_id]["status"] = "failed"
                        TASKS[task_id]["error"] = "超时拦截：任务执行超过 30 分钟限制，已由系统通过句柄安全销毁。"
                
    except OSError:
        async with tasks_state_lock:
            if task_id in TASKS:
                TASKS[task_id]["status"] = "error"
                TASKS[task_id]["error"] = "系统子进程调度异常: 权限不足或环境受限。"
    except Exception:
        async with tasks_state_lock:
            if task_id in TASKS:
                TASKS[task_id]["status"] = "error"
                TASKS[task_id]["error"] = "系统执行异常: 上下文保护错误。"
    finally:
        async with tasks_state_lock:
            if task_id in TASKS:
                TASKS[task_id]["end_time"] = datetime.now().isoformat()
        asyncio.create_task(save_and_prune_tasks_async())