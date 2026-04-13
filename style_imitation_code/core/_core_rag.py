import os
import json
import faiss
import numpy as np
import requests
import logging
import time
import collections
from threading import Lock
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# 屏蔽 transformers 模型加载时的非关键警告
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)

# =====================================================================
# 单例内存置换池 (保留问题三的修复：彻底切除 FAISS 内存堆积 OOM 风险)
# =====================================================================
class RAGCachePool:
    def __init__(self, capacity: int = 1):
        self.cache = collections.OrderedDict()
        self.capacity = capacity
        self.lock = Lock()

    def get(self, key: str):
        with self.lock:
            if key not in self.cache:
                return None
            return self.cache[key]

    def put(self, key: str, value: tuple):
        with self.lock:
            import gc
            
            if key in self.cache:
                old_val = self.cache.pop(key)
                del old_val
                gc.collect()  # 强制操作系统立即回收旧 FAISS 索引绑定的 C++ 堆内存
                
            self.cache[key] = value
            
            while len(self.cache) > self.capacity:
                _, popped_val = self.cache.popitem(last=False)
                del popped_val
                gc.collect()  # 强制操作系统立即回收淘汰的 C++ 堆内存

_global_rag_cache = RAGCachePool(capacity=1)

# =====================================================================
# 核心重构区：砍掉内部 RPC 代理，启用直连上游 API 的向量引擎
# =====================================================================
class DirectSiliconFlowEmbedder:
    """直接调用上游 SiliconFlow API 进行向量化，彻底斩断对本地 8000 端口的脆弱 RPC 依赖"""
    def __init__(self):
        # 确保在脱离 Web 主进程独立运行脚本时，依然能正确加载环境变量
        load_dotenv()
        
        self.api_key = os.environ.get("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise ValueError("【系统拦截】未配置 SILICONFLOW_API_KEY 环境变量，无法启动向量化引擎。请检查 .env 文件。")
            
        self.endpoint = "https://api.siliconflow.cn/v1/embeddings"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        self.session = requests.Session()
        # 保留指数退避重试机制，应对公网 API 波动
        retry_strategy = Retry(
            total=5,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        
    def encode(self, texts, batch_size=8, show_progress_bar=False):
        if isinstance(texts, str):
            texts = [texts]
            
        all_embeddings = []
        total_chunks = len(texts)
        
        for i in range(0, total_chunks, batch_size):
            batch_texts = texts[i:i + batch_size]
            # 硅基流动 API 契约限制：强制过滤纯空字符串，防止 400 报错
            safe_texts = [t if t.strip() else " " for t in batch_texts]
            
            payload = {
                "model": "BAAI/bge-m3", 
                "input": safe_texts
            }
            
            try:
                response = self.session.post(self.endpoint, headers=self.headers, json=payload, timeout=120)
                response.raise_for_status()
                
                data = response.json()
                embeddings = [item["embedding"] for item in data["data"]]
                all_embeddings.extend(embeddings)
                
                if show_progress_bar:
                    current = min(i + batch_size, total_chunks)
                    print(f"[INFO] 向量化批处理进度: {current} / {total_chunks} 块", flush=True)
                
                # 基础防抖，防触发 API 厂商 429 并发速率拦截
                time.sleep(0.2)
                    
            except requests.exceptions.RequestException as e:
                status_code = getattr(e.response, 'status_code', None)
                print(f"[ERROR] 调用第三方向量模型失败 (状态码: {status_code}): {e}")
                raise RuntimeError("请求底层向量化引擎网络超时或被拒，已拦截堆栈。")
            except KeyError as ke:
                print(f"[ERROR] 第三方向量服务响应结构变动: 缺失键 {ke}")
                raise RuntimeError("上游模型返回的数据结构发生未预期的变动。")
                
        return np.array(all_embeddings, dtype='float32')

class RAGRetriever:
    def __init__(self):
        self.embedder = None

    def get_embedder(self):
        """延迟加载 Embedding 模型，采用全局单例模式"""
        if self.embedder is None:
            self.embedder = DirectSiliconFlowEmbedder()
        return self.embedder

    def load_index(self, index_path, chunks_path):
        """带有内存缓存与安全路径校验的索引加载器"""
        if not os.path.exists(index_path) or not os.path.exists(chunks_path):
             raise FileNotFoundError("未找到 RAG 索引文件或元数据块。")

        safe_index_path = os.path.normcase(os.path.realpath(os.path.abspath(index_path)))
        safe_chunks_path = os.path.normcase(os.path.realpath(os.path.abspath(chunks_path)))

        try:
            index_mtime = os.path.getmtime(safe_index_path)
            cache_key = f"{safe_index_path}_{index_mtime}"
        except OSError:
            raise RuntimeError("系统错误：无法读取目标存储卷的文件状态凭证。")

        cached_data = _global_rag_cache.get(cache_key)
        if cached_data is not None:
            return cached_data[0], cached_data[1]

        try:
            index = faiss.read_index(safe_index_path)
            with open(safe_chunks_path, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            
            _global_rag_cache.put(cache_key, (index, chunks))
            return index, chunks
        except OSError:
            raise RuntimeError("系统拦截：索引文件读取遭遇底层存储设备 I/O 拒绝或权限不足。")
        except json.JSONDecodeError:
            raise RuntimeError("系统拦截：向量元数据块 (chunks) JSON 结构已损坏。")

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
                    chunk_data = chunks[idx]
                    if isinstance(chunk_data, dict):
                        retrieved_chunks.add(chunk_data.get("raw_chunk", chunk_data.get("text", "")))
                    else:
                        retrieved_chunks.add(chunk_data)
                        
        return list(retrieved_chunks)