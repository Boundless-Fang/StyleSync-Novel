import os
import traceback
import asyncio
import requests
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

# 全局限流信号量，保护主线程池不被第三方长耗时阻塞打穿
embed_semaphore = asyncio.Semaphore(5)

@router.post("/api/internal/embed")
async def internal_embed(req: EmbedRequest):
    """供本地子进程调用的内部向量化高速接口 (安全容错与异步隔离版)"""
    
    EMBEDDING_API_KEY = os.environ.get("SILICONFLOW_API_KEY")
    if not EMBEDDING_API_KEY:
        raise HTTPException(status_code=500, detail="【系统拦截】未配置硅基流动 API Key，拒绝请求。")
        
    EMBEDDING_BASE_URL = "https://api.siliconflow.cn/v1/embeddings"
    
    safe_texts = [t if t.strip() else " " for t in req.texts]

    headers = {
        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "BAAI/bge-m3", 
        "input": safe_texts
    }
    
    async with embed_semaphore:
        try:
            # 通过 to_thread 将底层的同步阻塞 I/O 强制卸载至后台守护线程执行
            response = await asyncio.to_thread(
                requests.post, 
                EMBEDDING_BASE_URL, 
                headers=headers, 
                json=payload, 
                timeout=120
            )
            
            if response.status_code != 200:
                print(f"[ERROR] 硅基流动网关拒绝请求，状态码: {response.status_code}, 详情: {response.text}")
                raise HTTPException(status_code=502, detail="上游模型服务提供商网关异常或拒绝响应")
            
            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
            return {"embeddings": embeddings}
            
        except requests.exceptions.RequestException as re_exc:
            print(f"[ERROR] 请求第三方向量服务发生网络底层异常: {re_exc}")
            raise HTTPException(status_code=504, detail="请求上游模型服务网络超时或物理连接失败")
        except KeyError as ke:
            print(f"[ERROR] 第三方向量服务响应结构变动: 缺失键 {ke}")
            raise HTTPException(status_code=500, detail="上游模型返回的数据结构发生未预期的变动")

# =====================================================================

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
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                
                if getattr(chunk, 'usage', None) and chunk.usage:
                    yield f"__USAGE__:{chunk.usage.prompt_tokens},{chunk.usage.completion_tokens}__"
                    
        except Exception as e:
            yield f"\n\n[系统请求错误: {str(e)}]"

    return StreamingResponse(generate(), media_type="text/plain")