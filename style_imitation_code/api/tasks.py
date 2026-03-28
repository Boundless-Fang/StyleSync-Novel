# --- File: tasks.py ---
import os
import asyncio
import re
from datetime import datetime

# =====================================================================
# --- 系统全局并发控制 ---
# 分离后台任务与流式生成的并发锁，防止长耗时任务阻塞前端请求
# =====================================================================
background_semaphore = asyncio.Semaphore(1)  # 后台排队锁 (用于 f0-f5a 等重负荷切分、总结任务)
stream_semaphore = asyncio.Semaphore(3)      # 流式生成锁 (用于 f5b 正文生成，允许一定并发防止前端504)
TASKS = {}

async def run_task_safely(task_id: str, cmd_list: list, api_key: str = None):
    TASKS[task_id]["status"] = "running"
    TASKS[task_id]["start_time"] = datetime.now().isoformat()
    TASKS[task_id]["stdout"] = ""  # 初始化为空字符串
    TASKS[task_id]["stderr"] = ""
    TASKS[task_id]["tokens"] = 0
    
    env = os.environ.copy()
    if api_key:
        env["DEEPSEEK_API_KEY"] = api_key
        
    try:
        async with background_semaphore:
            process = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            # 【核心修复】：实时读取子进程标准输出管道，防止积压，实现进度条推送前端
            async def pipe_reader(stream, key):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded_line = line.decode('utf-8', errors='replace')
                    TASKS[task_id][key] += decoded_line
                    
                    # 动态更新 Token 消耗
                    if key == "stdout":
                        token_matches = re.findall(r'(?:[Tt]okens?|消耗)[:=：\s]*(\d+)', decoded_line)
                        if token_matches:
                            TASKS[task_id]["tokens"] = int(token_matches[-1])

            try:
                # 并发等待输出流读取和进程结束
                await asyncio.wait_for(
                    asyncio.gather(
                        pipe_reader(process.stdout, "stdout"),
                        pipe_reader(process.stderr, "stderr"),
                        process.wait()
                    ),
                    timeout=1800.0  # 30分钟超时拦截
                )
                
                TASKS[task_id]["returncode"] = process.returncode
                if process.returncode == 0:
                    TASKS[task_id]["status"] = "success"
                else:
                    TASKS[task_id]["status"] = "failed"
                    
            except asyncio.TimeoutError:
                process.kill()
                TASKS[task_id]["status"] = "failed"
                TASKS[task_id]["error"] = "超时异常：任务执行超过设定时间 (30分钟)，已被后台强制终止拦截以防止僵尸进程。"
                
    except Exception as e:
        TASKS[task_id]["status"] = "error"
        TASKS[task_id]["error"] = str(e)
    finally:
        TASKS[task_id]["end_time"] = datetime.now().isoformat()