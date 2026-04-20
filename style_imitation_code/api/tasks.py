import os
import json
import asyncio
import re
import sys
import time
import subprocess
from datetime import datetime
from .config import PROJ_DIR, CODE_DIR

# 引入核心层的原子写与安全模块
from core._core_utils import atomic_write, async_atomic_write, mask_sensitive_info

# 系统全局并发控制与防护
background_semaphore = asyncio.Semaphore(1)
stream_semaphore = asyncio.Semaphore(3)

# 核心任务字典与持久化配置
TASKS = {}
TASKS_DB_PATH = os.path.join(PROJ_DIR, "system_tasks_db.json")
MAX_RETAINED_TASKS = 50

# 全局日志内存高水位线（单通道最多保留 15000 字符，约 5000 汉字，足够前端滚动查看）
MAX_LOG_BUFFER_LENGTH = 15000

# =====================================================================
# 看门狗与幽灵进程监控池配置
# =====================================================================
ACTIVE_PROCESSES = {}  # 记录正在运行的 task_id -> process 对象映射
TASK_STALL_TIMEOUT = 300  # 看门狗判定死锁阈值：5分钟无任何 stdout/stderr 输出
_watchdog_started = False  # 确保看门狗只启动一次

# I/O 互斥锁，防止并发写盘损坏文件
db_save_lock = asyncio.Lock()
# 内存状态互斥锁，严格保护 TASKS 字典的读写原子性
tasks_state_lock = asyncio.Lock()
# 监控池互斥锁，严格保护 ACTIVE_PROCESSES 防止迭代时字典改变大小引发并发异常
active_procs_lock = asyncio.Lock()
ACTIVE_TASK_STATUSES = {"running", "pending", "queued"}


def _task_sort_key(task: dict) -> str:
    return task.get("start_time") or task.get("created_at") or ""


def _append_task_log(task: dict, message: str, key: str = "stdout"):
    existing = task.get(key, "")
    merged_text = f"{existing}{message}"
    task[key] = merged_text[-MAX_LOG_BUFFER_LENGTH:]


def _mark_task_cancelled(task: dict, reason: str):
    task["status"] = "cancelled"
    task["error"] = reason
    task["end_time"] = datetime.now().isoformat()
    _append_task_log(task, f"\n[SYSTEM] {reason}\n")


async def _terminate_process(process):
    if not process:
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        await process.wait()
    except (OSError, ProcessLookupError):
        pass


async def cancel_task_by_id(task_id: str, reason: str = "用户手动终止任务"):
    async with tasks_state_lock:
        task = TASKS.get(task_id)
        if not task:
            return None
        if task.get("status") not in ACTIVE_TASK_STATUSES:
            return {
                "task_id": task_id,
                "task_name": task.get("name", task_id),
                "already_finished": True,
                "status": task.get("status"),
            }
        _mark_task_cancelled(task, reason)
        task_name = task.get("name", task_id)

    async with active_procs_lock:
        process = ACTIVE_PROCESSES.get(task_id)

    await _terminate_process(process)
    asyncio.create_task(save_and_prune_tasks_async())
    return {"task_id": task_id, "task_name": task_name, "already_finished": False}


async def cancel_latest_task(reason: str = "用户手动终止最近任务"):
    async with tasks_state_lock:
        active_items = [
            (task_id, task)
            for task_id, task in TASKS.items()
            if task.get("status") in ACTIVE_TASK_STATUSES
        ]
        if not active_items:
            return None
        task_id, _ = max(active_items, key=lambda item: _task_sort_key(item[1]))

    return await cancel_task_by_id(task_id, reason=reason)


async def cancel_all_tasks(reason: str = "用户手动终止全部任务"):
    async with tasks_state_lock:
        task_ids = [
            task_id
            for task_id, task in TASKS.items()
            if task.get("status") in ACTIVE_TASK_STATUSES
        ]

    cancelled = []
    for task_id in task_ids:
        result = await cancel_task_by_id(task_id, reason=reason)
        if result and not result.get("already_finished"):
            cancelled.append(result)
    return cancelled

def load_tasks_safe():
    """防线四：启动时的防尸变机制 - 懒加载自愈方案"""
    global TASKS
    if os.path.exists(TASKS_DB_PATH):
        try:
            with open(TASKS_DB_PATH, 'r', encoding='utf-8') as f:
                loaded_tasks = json.load(f)
            for t_id, t_info in loaded_tasks.items():
                if t_info.get("status") in ["running", "pending", "queued"]:
                    t_info["status"] = "failed"
                    t_info["error"] = "系统重启：历史中断任务已清理。"
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
                if v.get("status") not in ["running", "pending", "queued"]
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
            await async_atomic_write(TASKS_DB_PATH, snapshot, 'json')
        except (RuntimeError, OSError) as e:
            print(f"[ERROR] 任务状态落盘失败: {mask_sensitive_info(str(e))}")

# =====================================================================
# 自动化看门狗（Zombie Reaper）核心逻辑
# =====================================================================
async def start_watchdog_if_needed():
    global _watchdog_started
    if not _watchdog_started:
        _watchdog_started = True
        asyncio.create_task(zombie_reaper_loop())

async def zombie_reaper_loop():
    """后台常驻巡检，专杀占压 Semaphore 的幽灵进程"""
    while True:
        await asyncio.sleep(60)  # 每 60 秒扫街一次
        current_time = time.time()
        
        # 提取快照，防止与主事件循环产生死锁或竞态条件
        async with active_procs_lock:
            procs_snapshot = list(ACTIVE_PROCESSES.items())
        
        async with tasks_state_lock:
            for task_id, proc in procs_snapshot:
                task = TASKS.get(task_id)
                if task and task.get("status") == "running":
                    last_active = task.get("last_active_time", current_time)
                    # 判定死锁：超过阈值没有任何管道输出
                    if current_time - last_active > TASK_STALL_TIMEOUT:
                        print(f"[WATCHDOG ALARM] 发现幽灵进程死锁 (TaskID: {task_id})，强制执行物理收割！")
                        try:
                            # 调用 Windows 系统原生命令，强行终结进程树，防止任何孙进程残留
                            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True, check=False)
                            task["error"] = f"【系统看门狗介入】检测到进程超过 {TASK_STALL_TIMEOUT} 秒无任何响应输出，疑似陷入底层死锁，已被强制收割释放。"
                            task["status"] = "failed"
                        except Exception as e:
                            print(f"[WATCHDOG ERROR] 收割失败: {e}")

async def run_task_safely_pool(task_id: str, module_name: str, func_name: str, kwargs: dict, api_key: str = None):
    """
    为了兼容独立进程架构提供的过渡代理函数。
    """
    cmd = [sys.executable, "-m", module_name]
    for k, v in kwargs.items():
        if isinstance(v, bool):
            if v: cmd.append(f"--{k}")
        else:
            cmd.extend([f"--{k}", str(v)])
    
    await run_task_safely(task_id, cmd, api_key)


async def run_task_safely(task_id: str, cmd_list: list, api_key: str = None):
    """
    核心异步调度器：
    重构了状态机的精准生命周期管控，消灭伪运行状态。
    """
    # 确保看门狗始终处于待命状态
    await start_watchdog_if_needed()
    
    async with tasks_state_lock:
        if task_id in TASKS:
            TASKS[task_id]["status"] = "queued"
            # 移除暴露底层的锁日志，改为面向业务的清爽提示
            TASKS[task_id]["stdout"] = "[系统调度] 任务已就绪，正在准备启动处理引擎...\n"
            TASKS[task_id]["stderr"] = ""
            TASKS[task_id]["tokens"] = 0
            TASKS[task_id]["last_active_time"] = time.time()
    
    asyncio.create_task(save_and_prune_tasks_async())
    
    env = os.environ.copy()
    
    # 【核心修复：打通管道缓冲】强制关闭 Python 在非终端环境下的标准输出块缓冲，实现实时推流
    env["PYTHONUNBUFFERED"] = "1"
    
    if api_key:
        env["DEEPSEEK_API_KEY"] = api_key
    if not (env.get("SILICONFLOW_API_KEY") or "").strip():
        for alias in ("EMBEDDING_API_KEY", "SILICONFLOW_KEY", "SILICONFLOW_APIKEY"):
            alias_val = (env.get(alias) or "").strip()
            if alias_val:
                env["SILICONFLOW_API_KEY"] = alias_val
                break
    env["PYTHONIOENCODING"] = "utf-8"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        CODE_DIR if not existing_pythonpath
        else os.pathsep.join([CODE_DIR, existing_pythonpath])
    )
        
    try:
        # 排队获取并发锁
        async with background_semaphore:
            async with tasks_state_lock:
                if task_id not in TASKS or TASKS[task_id].get("status") == "cancelled":
                    return
                TASKS[task_id]["status"] = "running"
                TASKS[task_id]["start_time"] = datetime.now().isoformat()
                TASKS[task_id]["last_active_time"] = time.time()
                TASKS[task_id]["stdout"] = "[系统] 引擎启动成功，开始执行底层计算流：\n"

            process = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=CODE_DIR
            )
            
            # 将进程安全注册进看门狗巡检池
            async with active_procs_lock:
                ACTIVE_PROCESSES[task_id] = process

            async with tasks_state_lock:
                cancelled_before_reader = (
                    task_id not in TASKS or TASKS[task_id].get("status") == "cancelled"
                )
            if cancelled_before_reader:
                await _terminate_process(process)
                return
            
            async def pipe_reader(stream, key):
                while True:
                    try:
                        line = await stream.readline()
                        if not line: break
                    except asyncio.LimitOverrunError:
                        try:
                            trash_data = await stream.read(65536)  # 强行吸除 64KB 垃圾
                            if not trash_data: break
                            # 使用动态编码而非字节字面量，避开 Python 解释器的非 ASCII 字符校验拦截
                            line = "\n[SYSTEM WARN] 子进程输出了超长无换行数据，触发 OS 管道溢出保护，已执行强制截断清理...\n".encode('utf-8')
                        except Exception:
                            break
                    except OSError:
                        break
                    
                    try:
                        decoded_line = line.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded_line = line.decode('gbk', errors='replace')
                    
                    async with tasks_state_lock:
                        if task_id in TASKS:
                            TASKS[task_id]["last_active_time"] = time.time()
                            
                            if key == "stdout":
                                token_matches = re.findall(r'(?:[Tt]okens?|消耗)[:=：\s]*(\d+)', decoded_line)
                                if token_matches:
                                    TASKS[task_id]["tokens"] = int(token_matches[-1])

                            merged_text = TASKS[task_id][key] + decoded_line
                            TASKS[task_id][key] = merged_text[-MAX_LOG_BUFFER_LENGTH:]

            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        pipe_reader(process.stdout, "stdout"),
                        pipe_reader(process.stderr, "stderr"),
                        process.wait()
                    ),
                    timeout=1800.0  # 保留底线的绝对 30 分钟超时
                )
                
                async with tasks_state_lock:
                    if task_id in TASKS:
                        if TASKS[task_id].get("status") not in {"failed", "cancelled"}:
                            TASKS[task_id]["returncode"] = process.returncode
                            TASKS[task_id]["status"] = "success" if process.returncode == 0 else "failed"
                                
            except asyncio.TimeoutError: 
                try: 
                    # 使用 Windows 系统原生命令，强行终结进程树
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True, check=False)
                    await process.wait() 
                except OSError: 
                    pass
                    
                async with tasks_state_lock:
                    if task_id in TASKS:
                        TASKS[task_id]["status"] = "failed"
                        TASKS[task_id]["error"] = "绝对超时拦截：任务执行超 30 分钟极限阈值，已执行强制安全释放。"
            
            finally:
                # 无论如何退出，安全移出监控池
                async with active_procs_lock:
                    ACTIVE_PROCESSES.pop(task_id, None)
                
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
