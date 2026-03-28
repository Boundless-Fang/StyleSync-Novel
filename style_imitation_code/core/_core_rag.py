import os
import json
import shutil
import faiss
import numpy as np
import uuid
import requests
import logging

# 屏蔽 transformers 模型加载时的非关键警告
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)

# =====================================================================
# 引入轻量级代理类，将编码请求发送给常驻内存的 FastAPI 主进程
# =====================================================================
class RemoteEmbedder:
    """拦截原有的本地算力调用，转交 FastAPI 主进程完成，避免子进程暴起 2.2GB 内存"""
    def __init__(self, endpoint=None):
        # 如果未传入 endpoint，优先读取环境变量，没有环境变量则兜底使用 127.0.0.1:8000
        if endpoint is None:
            base_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
            self.endpoint = f"{base_url}/api/internal/embed"
        else:
            self.endpoint = endpoint
        
    def encode(self, texts, batch_size=8, show_progress_bar=False):
        # 如果传入的是单条文本，转为列表
        if isinstance(texts, str):
            texts = [texts]
            
        all_embeddings = []
        total_chunks = len(texts)
        
        # 【致命 Bug 修复】：强制引入批处理逻辑，避免全量数据一把梭导致主进程噎死或超时
        for i in range(0, total_chunks, batch_size):
            batch_texts = texts[i:i + batch_size]
            try:
                # 向主进程发起轻量级 HTTP 请求获取向量矩阵
                response = requests.post(self.endpoint, json={"texts": batch_texts}, timeout=120)
                response.raise_for_status()
                
                # 收集该批次的向量结果
                all_embeddings.extend(response.json()["embeddings"])
                
                # 同步打印进度，强制 flush 吐给前端，避免假死感
                if show_progress_bar:
                    current = min(i + batch_size, total_chunks)
                    print(f"🚀 向量化批处理进度: {current} / {total_chunks} 块", flush=True)
                    
            except Exception as e:
                print(f"⚠️ 调用主进程向量模型失败 (批次 {i} - {i+batch_size}): {e}")
                raise
                
        # 还原为原版 SentenceTransformer 产出的 numpy 矩阵格式，完美欺骗外层调用链
        return np.array(all_embeddings, dtype='float32')

class RAGRetriever:
    def __init__(self):
        self.embedder = None

    def get_embedder(self):
        """延迟加载 Embedding 模型，采用全局单例模式"""
        if self.embedder is None:
            # 不再初始化 SentenceTransformer，而是直接返回代理类实例
            self.embedder = RemoteEmbedder()
        return self.embedder

    def load_index(self, index_path, chunks_path):
        """安全加载 FAISS 索引与文本块映射数据"""
        if not os.path.exists(index_path) or not os.path.exists(chunks_path):
             raise FileNotFoundError("未找到 RAG 索引文件。")

        # 使用 uuid 生成唯一临时文件，彻底规避并发锁死和残留污染问题
        unique_id = uuid.uuid4().hex
        temp_read_path = f"temp_read_index_{unique_id}.bin"
        
        shutil.copy2(index_path, temp_read_path)
        index = faiss.read_index(temp_read_path)
        
        try:
            os.remove(temp_read_path)
        except OSError:
            pass
            
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
            
        return index, chunks

    def search(self, index, chunks, queries, k=6, batch_size=5):
        """执行批处理编码与检索，返回去重后的上下文集合"""
        embedder = self.get_embedder()
        retrieved_chunks = set()
        
        for i in range(0, len(queries), batch_size):
            batch_queries = [" ".join(queries[i:i+batch_size])]
            query_vec = embedder.encode(batch_queries)
            distances, indices = index.search(np.array(query_vec).astype('float32'), k)
            
            for idx in indices[0]:
                if idx != -1 and idx < len(chunks):
                    # 兼容不同结构的 chunks 数据 (字典或纯文本)
                    chunk_data = chunks[idx]
                    if isinstance(chunk_data, dict):
                        retrieved_chunks.add(chunk_data.get("raw_chunk", chunk_data.get("text", "")))
                    else:
                        retrieved_chunks.add(chunk_data)
                        
        return list(retrieved_chunks)