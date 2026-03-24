import os
import asyncio
import re
from datetime import datetime

# =====================================================================
# --- 2. 系统全局并发控制 ---
# 分离后台任务与流式生成的并发锁，防止长耗时任务阻塞前端请求
# =====================================================================
background_semaphore = asyncio.Semaphore(1)  # 后台排队锁 (用于 f0-f5a 等重负荷切分、总结任务)
stream_semaphore = asyncio.Semaphore(3)      # 流式生成锁 (用于 f5b 正文生成，允许一定并发防止前端504)
TASKS = {}

async def run_task_safely(task_id: str, cmd_list: list, api_key: str = None):
    TASKS[task_id]["status"] = "running"
    TASKS[task_id]["start_time"] = datetime.now().isoformat()
    
    env = os.environ.copy()
    if api_key:
        env["DEEPSEEK_API_KEY"] = api_key
        
    try:
        # 子进程任务执行改用专属的后台锁
        async with background_semaphore:
            process = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            try:
                # 设置最大30分钟的超时限制，超时则斩杀进程
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=1800.0)
                
                stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
                stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""
                
                TASKS[task_id]["returncode"] = process.returncode
                TASKS[task_id]["stdout"] = stdout_str
                TASKS[task_id]["stderr"] = stderr_str
                
                # 提取 usage 并按前端格式返回以便前端正则拦截
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