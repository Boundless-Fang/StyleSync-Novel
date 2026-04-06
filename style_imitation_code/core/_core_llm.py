import os 
import json 
import time 
import requests 
from dotenv import load_dotenv 
  
# 确保加载环境变量 
load_dotenv() 
  
def call_deepseek_api(system_prompt, user_prompt, model="deepseek-chat", temperature=0.5, max_retries=3): 
    """ 
    统一封装的非流式 LLM 请求 (带指数退避重试机制) 
    用于信息提取、设定补全、大纲生成等需要一次性返回完整结果的场景。 
    """ 
    api_key = os.getenv("DEEPSEEK_API_KEY") 
    if not api_key: 
        raise ValueError("error: 未能在环境变量中找到 DEEPSEEK_API_KEY") 
  
    headers = { 
        "Content-Type": "application/json",  
        "Authorization": f"Bearer {api_key}" 
    } 
     
    payload = { 
        "model": model, 
        "messages": [ 
            {"role": "system", "content": system_prompt}, 
            {"role": "user", "content": user_prompt} 
        ], 
        "temperature": temperature, 
        "stream": False 
    } 
     
    for attempt in range(max_retries): 
        try: 
            response = requests.post( 
                "https://api.deepseek.com/chat/completions",  
                headers=headers,  
                json=payload,  
                timeout=(10, 600)  # 连接给 10秒，读取放宽到 600秒(10分钟)以防 R1 深度思考 
            ) 
            response.raise_for_status() 
            data = response.json() 
             
            if 'usage' in data: 
                total_tokens = data['usage'].get('total_tokens', 0) 
                print(f"\nTotal Tokens: {total_tokens}", flush=True) 
                 
            return data['choices'][0]['message']['content'] 
             
        except requests.exceptions.RequestException as e: 
            status_code = getattr(e.response, 'status_code', None) 
            # 精准捕获限流与网关类异常进行退避重试 
            if status_code in [429, 500, 502, 503, 504] and attempt < max_retries - 1: 
                sleep_time = 2 ** attempt 
                print(f"[WARN] API 请求触发限流或网关无响应 (状态码: {status_code})，{sleep_time} 秒后进行第 {attempt + 1} 次重试...", flush=True) 
                time.sleep(sleep_time) 
                continue 
            raise RuntimeError(f"DeepSeek API 请求彻底失败 (已重试 {attempt} 次): {str(e)}") 
  
def stream_deepseek_api(system_prompt, user_prompt, model="deepseek-chat", temperature=0.5, max_retries=3): 
    """ 
    统一封装对大语言模型 API 的流式 (Streaming) HTTP 请求 (带握手期指数退避重试机制) 
    返回生成器，专门用于 f5b 正文生成等需要实时打字机效果的场景。 
    """ 
    api_key = os.getenv("DEEPSEEK_API_KEY") 
    if not api_key: 
        raise ValueError("error: 未能在环境变量中找到 DEEPSEEK_API_KEY") 
  
    headers = { 
        "Content-Type": "application/json",  
        "Authorization": f"Bearer {api_key}" 
    } 
     
    payload = { 
        "model": model, 
        "messages": [ 
            {"role": "system", "content": system_prompt}, 
            {"role": "user", "content": user_prompt} 
        ], 
        "temperature": temperature, 
        "stream": True, 
        "stream_options": {"include_usage": True}  
    } 
     
    for attempt in range(max_retries): 
        try: 
            with requests.post( 
                "https://api.deepseek.com/chat/completions",  
                headers=headers,  
                json=payload,  
                stream=True,  
                timeout=(10, 300)  
            ) as response: 
                response.raise_for_status() 
                 
                for line in response.iter_lines(): 
                    if line: 
                        decoded_line = line.decode('utf-8') 
                        if decoded_line.startswith('data: ') and decoded_line != 'data: [DONE]': 
                            try: 
                                json_data = json.loads(decoded_line[6:]) 
                                 
                                if 'usage' in json_data and json_data['usage']: 
                                    total_tokens = json_data['usage'].get('total_tokens', 0) 
                                    print(f"\nTotal Tokens: {total_tokens}", flush=True) 
                                    continue 
                                     
                                if 'choices' in json_data and len(json_data['choices']) > 0: 
                                    delta_content = json_data['choices'][0]['delta'].get('content', '') 
                                    if delta_content: 
                                        yield delta_content  
                            except json.JSONDecodeError: 
                                continue 
                return # 正常传输完毕，安全退出 
                  
        except requests.exceptions.RequestException as e: 
            status_code = getattr(e.response, 'status_code', None) 
            if status_code in [429, 500, 502, 503, 504] and attempt < max_retries - 1: 
                sleep_time = 2 ** attempt 
                print(f"\n[WARN] 流式 API 建连阶段异常 (状态码: {status_code})，{sleep_time} 秒后进行第 {attempt + 1} 次重试...", flush=True) 
                time.sleep(sleep_time) 
                continue 
            raise RuntimeError(f"DeepSeek 流式 API 请求彻底失败: {str(e)}") 
