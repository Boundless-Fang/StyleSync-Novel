# --- File: routecore.py ---
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

from .config import CODE_DIR
from .models import ChatRequest

router = APIRouter()

# =====================================================================
# 全局常驻内存的 Embedding 模型服务生命周期与内部路由
# =====================================================================
class EmbedRequest(BaseModel):
    texts: list[str]

GLOBAL_EMBEDDER = None

@router.on_event("startup")
async def load_embedder():
    global GLOBAL_EMBEDDER
    print("🚀 正在预热加载全局 Embedding 模型 (BAAI/bge-m3)...")
    # 整个 FastAPI 生命周期内仅实例化一次，常驻内存，耗时仅发生在启动阶段
    GLOBAL_EMBEDDER = SentenceTransformer('BAAI/bge-m3')
    print("✅ 全局 Embedding 模型加载完成，子进程 RAG 调用将实现毫秒级响应！")

@router.post("/api/internal/embed")
async def internal_embed(req: EmbedRequest):
    """供本地子进程调用的内部向量化高速接口"""
    if GLOBAL_EMBEDDER is None:
        raise HTTPException(status_code=500, detail="全局 Embedding 模型尚未加载完成")
    
    # 在主进程内极速计算向量并打包返回给 _core_rag 的 RemoteEmbedder
    embeddings = GLOBAL_EMBEDDER.encode(req.texts, show_progress_bar=False)
    return {"embeddings": embeddings.tolist()}
# =====================================================================

# --- 基础 API 路由 ---
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