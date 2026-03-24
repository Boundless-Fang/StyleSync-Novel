import sys
import argparse
import os
import json
import numpy as np
import warnings
import logging
import shutil
import faiss
import re

# =====================================================================
# 1. 跨目录寻址：将父目录(style_imitation_code)加入环境变量
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__)) # 指向 scripts/
parent_dir = os.path.dirname(current_dir)                # 指向 style_imitation_code/
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# =====================================================================
# 2. 导入 core 模块 (注意加 core. 前缀)
# =====================================================================
from core._core_config import REFERENCE_DIR, STYLE_DIR
from core._core_utils import smart_read_text
from core._core_rag import RAGRetriever

class GlobalIndexerApp:
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
            print("⚠️ 未检测到标准章节标记，退回原始滑动窗口方案。")
            return GlobalIndexerApp.fallback_chunking(text)

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
    def run(target_file):
        if os.path.isabs(target_file):
            original_path = target_file
        else:
            original_path = os.path.join(REFERENCE_DIR, target_file)

        if not os.path.exists(original_path):
            sys.exit(1)

        novel_name = os.path.splitext(os.path.basename(original_path))[0]
        style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
        rag_db_dir = os.path.join(style_dir, "global_rag_db")
        os.makedirs(rag_db_dir, exist_ok=True)

        text = smart_read_text(original_path)
        
        # 执行混合动态切分
        processed_chunks = GlobalIndexerApp.split_by_chapters_smart(text)
        chunk_texts = [item["text"] for item in processed_chunks]
        
        print(f"✅ 章节识别完成：共生成 {len(processed_chunks)} 个语义块。")

        # 加载 BGE-M3 模型并执行向量化
        retriever = RAGRetriever()
        embedder = retriever.get_embedder()
        embeddings = embedder.encode(chunk_texts, batch_size=8, show_progress_bar=True)

        # 构建 FAISS 索引
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(np.array(embeddings).astype('float32'))

        # 保存索引与带元数据的文本块
        index_path = os.path.join(rag_db_dir, "vector.index")
        chunks_path = os.path.join(rag_db_dir, "chunks.json")

        with open(chunks_path, 'w', encoding='utf-8') as f:
            json.dump(processed_chunks, f, ensure_ascii=False, indent=2)

        temp_path = "temp_vector_index.bin"
        faiss.write_index(index, temp_path)
        shutil.move(temp_path, index_path)
        print(f"🚀 全局 RAG 索引构建成功，已保存至: {rag_db_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, required=True)
    args, _ = parser.parse_known_args()
    GlobalIndexerApp.run(args.target_file)