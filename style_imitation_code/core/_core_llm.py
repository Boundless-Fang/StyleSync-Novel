import os
import json
import requests
from dotenv import load_dotenv

# 确保加载环境变量
load_dotenv()

def call_deepseek_api(system_prompt, user_prompt, model="deepseek-chat", temperature=0.5):
    """
    统一封装的非流式 LLM 请求
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
    
    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions", 
            headers=headers, 
            json=payload, 
            timeout=(10, 600)  # 连接给 10秒，读取放宽到 600秒(10分钟)以防 R1 深度思考
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"DeepSeek API 请求失败: {str(e)}")


def stream_deepseek_api(system_prompt, user_prompt, model="deepseek-chat", temperature=0.5):
    """
    统一封装对大语言模型 API 的流式 (Streaming) HTTP 请求
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
        "stream": True # 开启流式输出
    }
    
    with requests.post(
        "https://api.deepseek.com/chat/completions", 
        headers=headers, 
        json=payload, 
        stream=True, 
        timeout=(10, 300)  # 流式首字响应放宽到 300秒(5分钟)
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: ') and decoded_line != 'data: [DONE]':
                    try:
                        json_data = json.loads(decoded_line[6:])
                        if 'choices' in json_data and len(json_data['choices']) > 0:
                            delta_content = json_data['choices'][0]['delta'].get('content', '')
                            if delta_content:
                                yield delta_content # 每次吐出一个字或词
                    except json.JSONDecodeError:
                        continue