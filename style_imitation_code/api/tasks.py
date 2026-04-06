import os
import json
import asyncio
import re
from datetime import datetime
from .config import PROJ_DIR

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
        except Exception as e:
            print(f"[WARN] 历史任务数据库加载失败，可能文件已损坏: {e}")

async def add_task_safe(task_id: str, task_info: dict):
    """提供给外部路由的安全写入接口，防止并发导致字典大小突变"""
    async with tasks_state_lock:
        TASKS[task_id] = task_info

async def save_and_prune_tasks_async():
    """防线一、二、三：状态快照、互斥锁与异步非阻塞写入"""
    async with db_save_lock:
        async with tasks_state_lock:
            # 1. 免疫保护与目标锁定
            finished_tasks = {
                k: v for k, v in TASKS.items()
                if v.get("status") not in ["running", "pending"]
            }
            
            # 2. 精准裁剪
            if len(finished_tasks) > MAX_RETAINED_TASKS:
                sorted_keys = sorted(
                    finished_tasks.keys(),
                    key=lambda k: finished_tasks[k].get('created_at', ''),
                    reverse=True
                )
                keys_to_delete = sorted_keys[MAX_RETAINED_TASKS:]
                for k in keys_to_delete:
                    TASKS.pop(k, None)

            # 3. 数据快照：字典浅拷贝定格状态
            snapshot = {k: v.copy() for k, v in TASKS.items()}

        # 4. 临时态隔离与原子写入 (I/O 线程卸载)
        def _write_to_disk():
            temp_path = TASKS_DB_PATH + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, TASKS_DB_PATH)

        try:
            await asyncio.to_thread(_write_to_disk)
        except Exception as e:
            print(f"[ERROR] 任务状态落盘失败: {e}")

async def run_task_safely(task_id: str, cmd_list: list, api_key: str = None):
    # 初始化运行状态时加锁保护
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
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    
                    try:
                        decoded_line = line.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded_line = line.decode('gbk', errors='replace')
                        
                    async with tasks_state_lock:
                        if task_id in TASKS:
                            TASKS[task_id][key] += decoded_line
                            if key == "stdout":
                                token_matches = re.findall(r'(?:[Tt]okens?|消耗)[:=：\s]*(\d+)', decoded_line)
                                if token_matches:
                                    TASKS[task_id]["tokens"] = int(token_matches[-1])

            try:
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
                        if process.returncode == 0:
                            TASKS[task_id]["status"] = "success"
                        else:
                            TASKS[task_id]["status"] = "failed"
                            
            except asyncio.TimeoutError:
                # 【核心修复】：阶梯式平滑终止机制
                try:
                    process.terminate()  # 发送 SIGTERM，允许子进程执行 finally 和 os.replace
                    await asyncio.sleep(5.0)  # 给予 5 秒事务回滚与宽限期
                    if process.returncode is None:
                        process.kill()  # 宽限期后若仍未退出，执行物理强杀 (SIGKILL)
                except Exception:
                    pass
                    
                async with tasks_state_lock:
                    if task_id in TASKS:
                        TASKS[task_id]["status"] = "failed"
                        TASKS[task_id]["error"] = "超时拦截：任务执行超过设定时间，已触发平滑终止与强制终结，底层写盘已受事务保护。"
                
    except Exception as e:
        async with tasks_state_lock:
            if task_id in TASKS:
                TASKS[task_id]["status"] = "error"
                TASKS[task_id]["error"] = f"系统执行异常: {str(e)}"
    finally:
        async with tasks_state_lock:
            if task_id in TASKS:
                TASKS[task_id]["end_time"] = datetime.now().isoformat()
        asyncio.create_task(save_and_prune_tasks_async())