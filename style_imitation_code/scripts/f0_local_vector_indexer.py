import os
import sys
import json
import numpy as np
import faiss
import re

from core._core_cli_runner import safe_run_app, inject_env, HeadlessBaseTask
inject_env()

from core._core_config import REFERENCE_DIR, STYLE_DIR
from core._core_utils import smart_read_text, atomic_write
from core._core_rag import RAGRetriever

class GlobalIndexerGUI(HeadlessBaseTask):
    def __init__(self):
        super().__init__()

    def execute_logic(self):
        pass

    @staticmethod
    def split_by_chapters_smart(text, threshold=3000):
        """
        【升级】：基于章节结构的智能动态切分算法
        1. 识别章节
        2. < 3000字整块保留
        3. >= 3000字在接近中点的自然段处切分
        """
        # 章节匹配正则 (同 f4b 标准)
        pattern = r'\n(第[零一二三四五六七八九十百千万\d]+[章卷回节].*?)\n'
        matches = list(re.finditer(pattern, "\n" + text))
        
        chunks_metadata = []
        
        # 如果没搜到章节，退回原始滑动窗口逻辑
        if not matches:
            print("[WARN] 未检测到标准章节标记，退回原始滑动窗口方案。")
            return GlobalIndexerGUI.fallback_chunking(text)

        for i in range(len(matches)):
            start_pos = matches[i].start()
            end_pos = matches[i+1].start() if i + 1 < len(matches) else len(text)
            
            chapter_title = matches[i].group(1).strip()
            chapter_content = text[start_pos:end_pos].strip()
            chapter_len = len(chapter_content)

            if chapter_len < threshold:
                # 3000字以下整切
                chunks_metadata.append({
                    "text": chapter_content,
                    "metadata": {"chapter": chapter_title, "index": i}
                })
            else:
                # 3000字以上弹性对半切
                # 寻找接近 1800-2000 字（中点附近）的下一个自然段
                mid_point = chapter_len // 2
                search_start = int(mid_point * 0.9)
                split_idx = chapter_content.find('\n', search_start)
                
                if split_idx != -1 and split_idx < chapter_len * 0.9:
                    # 第一部分
                    chunks_metadata.append({
                        "text": chapter_content[:split_idx].strip(),
                        "metadata": {"chapter": chapter_title, "index": i, "part": 1}
                    })
                    # 第二部分
                    chunks_metadata.append({
                        "text": chapter_content[split_idx:].strip(),
                        "metadata": {"chapter": chapter_title, "index": i, "part": 2}
                    })
                else:
                    # 如果找不到合适的自然段，则整章保留
                    chunks_metadata.append({
                        "text": chapter_content,
                        "metadata": {"chapter": chapter_title, "index": i}
                    })
        
        return chunks_metadata

    @staticmethod
    def fallback_chunking(text, max_len=2000, overlap=300):
        """原始滑动窗口兜底方案"""
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        chunks = []
        current_chunk = ""
        for p in paragraphs:
            if len(current_chunk) + len(p) <= max_len:
                current_chunk += p + "\n"
            else:
                if current_chunk: chunks.append(current_chunk.strip())
                current_chunk = current_chunk[-overlap:] + p + "\n" if len(current_chunk) > overlap else p + "\n"
        if current_chunk: chunks.append(current_chunk.strip())
        return [{"text": c, "metadata": {"chapter": "unknown"}} for c in chunks]

    @staticmethod
    def run_indexing(target_file, log_func=print):
        if os.path.isabs(target_file):
            original_path = target_file
        else:
            original_path = os.path.join(REFERENCE_DIR, target_file)

        if not os.path.exists(original_path):
            log_func(f"[ERROR] 未找到目标文件: {original_path}")
            return False

        novel_name = os.path.splitext(os.path.basename(original_path))[0]
        style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
        rag_db_dir = os.path.join(style_dir, "global_rag_db")
        os.makedirs(rag_db_dir, exist_ok=True)

        log_func(f"正在读取文本: {original_path}")
        text = smart_read_text(original_path)
        
        # 执行混合动态切分
        processed_chunks = GlobalIndexerGUI.split_by_chapters_smart(text)
        chunk_texts = [item["text"] for item in processed_chunks]
        
        log_func(f"[INFO] 章节 recognition 完成：共生成 {len(processed_chunks)} 个语义块。")

        # 加载 BGE-M3 模型并执行向量化
        log_func("正在初始化向量模型并生成 Embedding...")
        retriever = RAGRetriever()
        embedder = retriever.get_embedder()
        embeddings = embedder.encode(chunk_texts, batch_size=8, show_progress_bar=True)

        # 构建 FAISS 索引
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(np.array(embeddings).astype('float32'))

        # 保存索引与带元数据的文本块 (使用原子写入保护)
        index_path = os.path.join(rag_db_dir, "vector.index")
        chunks_path = os.path.join(rag_db_dir, "chunks.json")

        try:
            atomic_write(chunks_path, processed_chunks, data_type='json')
            atomic_write(index_path, index, data_type='faiss')
        except Exception as e:
            log_func(f"[ERROR] 索引文件落盘失败: {e}")
            return False
        log_func(f"[INFO] 全局 RAG 索引构建成功，已保存至: {rag_db_dir}")
        return True

def run_headless(target_file):
    success = GlobalIndexerGUI.run_indexing(target_file)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    safe_run_app(app_class=GlobalIndexerGUI, headless_func=run_headless, target_file="")
