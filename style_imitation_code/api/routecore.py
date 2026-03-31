# --- File: routecore.py ---
import os
import traceback
import requests  # 新增：原生 HTTP 请求库
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from .config import CODE_DIR
from .models import ChatRequest

router = APIRouter()

# =====================================================================
# 全局常驻内存的 Embedding 模型服务生命周期与内部路由 (云端原生 HTTP 版)
# =====================================================================
class EmbedRequest(BaseModel):
    texts: list[str]

# 注意：去掉了 async，避免在处理阻塞请求时产生异步冲突
@router.post("/api/internal/embed")
def internal_embed(req: EmbedRequest):
    """供本地子进程调用的内部向量化高速接口 (安全容错版)"""
    
    # 优先读环境变量，读不到就用你填写的真实 Key
    EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "sk-blrjxqvjrjpefkruqufxqyoiitfpaflpyhgxtv")
    # 注意加上了 /embeddings 后缀
    EMBEDDING_BASE_URL = "https://api.siliconflow.cn/v1/embeddings"
    
    # 【核心防爆修复】：强行把空串替换为空格，保持数组长度 1:1 绝对对齐，骗过大厂网关
    safe_texts = [t if t.strip() else " " for t in req.texts]

    headers = {
        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "BAAI/bge-m3", 
        "input": safe_texts
    }
    
    try:
        # 直接发送原生的 POST 请求
        response = requests.post(EMBEDDING_BASE_URL, headers=headers, json=payload, timeout=120)
        
        # 状态码拦截与官方真实报错打印
        if response.status_code != 200:
            print("\n" + "🔥"*25)
            print(f"🔴 硅基流动官方拒绝了请求！状态码: {response.status_code}")
            print(f"官方报错原文: {response.text}")
            print("🔥"*25 + "\n")
            raise HTTPException(status_code=500, detail=f"API 报错: {response.text}")
        
        data = response.json()
        # 完美提取向量数组
        embeddings = [item["embedding"] for item in data["data"]]
        return {"embeddings": embeddings}
        
    except Exception as e:
        print("\n" + "="*50)
        print("🔴 请求发生代码级异常或网络超时：")
        traceback.print_exc()
        print("="*50 + "\n")
        raise HTTPException(status_code=500, detail=str(e))
# =====================================================================

# --- 基础 API 路由 (对话部分保持不变) ---
# @router.get("/")
# async def serve_frontend():
#     return FileResponse(os.path.join(CODE_DIR, "index.html"))

@router.post("/api/chat")
async def chat_stream(req: ChatRequest):
    client = AsyncOpenAI(api_key=req.api_key, base_url="https://api.deepseek.com")
    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    messages.extend(req.messages)

    async def generate():
        try:
            stream = await client.chat.completions.create(
                model=req.model,
                messages=messages,
                stream=True,
                temperature=req.temperature,
                top_p=req.top_p,
                stream_options={"include_usage": True} 
            )
            async for chunk in stream:
                # 处理正常文本流
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                
                # 提取 usage 并按前端格式返回以便前端正则拦截
                if getattr(chunk, 'usage', None) and chunk.usage:
                    yield f"__USAGE__:{chunk.usage.prompt_tokens},{chunk.usage.completion_tokens}__"
                    
        except Exception as e:
            yield f"\n\n[系统请求错误: {str(e)}]"

    return StreamingResponse(generate(), media_type="text/plain")