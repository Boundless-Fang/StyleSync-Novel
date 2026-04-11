import os
import sys
import json
import numpy as np
import faiss
import re
import gc

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
        """标准内存直通车切分算法"""
        pattern = r'\n(第[零一二三四五六七八九十百千万\d]+[章卷回节].*?)\n'
        matches = list(re.finditer(pattern, "\n" + text))
        
        chunks_metadata = []
        if not matches:
            return GlobalIndexerGUI.fallback_chunking(text)

        for i in range(len(matches)):
            start_pos = matches[i].start()
            end_pos = matches[i+1].start() if i + 1 < len(matches) else len(text)
            
            chapter_title = matches[i].group(1).strip()
            chapter_content = text[start_pos:end_pos].strip()
            chapter_len = len(chapter_content)

            if chapter_len < threshold:
                chunks_metadata.append({
                    "text": chapter_content,
                    "metadata": {"chapter": chapter_title, "index": i}
                })
            else:
                mid_point = chapter_len // 2
                search_start = int(mid_point * 0.9)
                split_idx = chapter_content.find('\n', search_start)
                
                if split_idx != -1 and split_idx < chapter_len * 0.9:
                    chunks_metadata.append({
                        "text": chapter_content[:split_idx].strip(),
                        "metadata": {"chapter": chapter_title, "index": i, "part": 1}
                    })
                    chunks_metadata.append({
                        "text": chapter_content[split_idx:].strip(),
                        "metadata": {"chapter": chapter_title, "index": i, "part": 2}
                    })
                else:
                    chunks_metadata.append({
                        "text": chapter_content,
                        "metadata": {"chapter": chapter_title, "index": i}
                    })
        return chunks_metadata

    @staticmethod
    def fallback_chunking(text, max_len=2000, overlap=300):
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
    def read_blocks_stream(filepath, start_offset, block_size=3000):
        """重载模式：流式增量字节读取生成器"""
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(start_offset)
            buffer = ""
            while True:
                line = f.readline()
                if not line:
                    if buffer.strip():
                        yield buffer.strip(), f.tell()
                    break
                buffer += line
                if len(buffer) >= block_size:
                    yield buffer.strip(), f.tell()
                    buffer = ""

    @staticmethod
    def merge_index_parts(rag_db_dir, total_parts, log_func):
        """重载模式：终态碎片合并组装"""
        log_func("[INFO] 正在将所有临时碎片组装为全局向量库...")
        all_chunks = []
        main_index = None

        for p in range(1, total_parts + 1):
            idx_path = os.path.join(rag_db_dir, f"part_{p}.index")
            json_path = os.path.join(rag_db_dir, f"chunks_part_{p}.json")
            
            if not os.path.exists(idx_path) or not os.path.exists(json_path):
                continue
                
            with open(json_path, 'r', encoding='utf-8') as f:
                part_chunks = json.load(f)
                all_chunks.extend(part_chunks)
                
            part_index = faiss.read_index(idx_path)
            if main_index is None:
                # 深度克隆结构，防指针溢出
                main_index = faiss.IndexFlatL2(part_index.d)
            
            # 标准的 FAISS 平面索引合并，规避部分版本 merge_into 的 C++ 报错
            # 由于每次仅将单 part_index 向量抽入内存，防 OOM
            vectors = np.zeros((part_index.ntotal, part_index.d), dtype=np.float32)
            part_index.reconstruct_n(0, part_index.ntotal, vectors)
            main_index.add(vectors)
            
            # 及时释放局部大内存块
            del part_index
            del vectors
            gc.collect()

        final_index_path = os.path.join(rag_db_dir, "vector.index")
        final_chunks_path = os.path.join(rag_db_dir, "chunks.json")
        
        atomic_write(final_chunks_path, all_chunks, data_type='json')
        atomic_write(final_index_path, main_index, data_type='faiss')
        
        # 清扫战场
        for p in range(1, total_parts + 1):
            try:
                os.remove(os.path.join(rag_db_dir, f"part_{p}.index"))
                os.remove(os.path.join(rag_db_dir, f"chunks_part_{p}.json"))
            except OSError:
                pass
        
        cp_path = os.path.join(rag_db_dir, "checkpoint.json")
        if os.path.exists(cp_path):
            os.remove(cp_path)
            
        log_func(f"[INFO] 碎片合并完毕，全局 RAG 索引落盘成功！共包含 {len(all_chunks)} 个文本块。")

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

        # 阶段一：文件体积嗅探与动静路由
        file_size = os.path.getsize(original_path)
        THRESHOLD_10MB = 10 * 1024 * 1024

        if file_size < THRESHOLD_10MB:
            # ==========================================
            # 内存直通车模式
            # ==========================================
            log_func(f"[INFO] 文件尺寸 ({file_size/1024/1024:.2f} MB) < 10MB，触发内存直通车极速模式...")
            text = smart_read_text(original_path)
            processed_chunks = GlobalIndexerGUI.split_by_chapters_smart(text)
            chunk_texts = [item["text"] for item in processed_chunks]
            
            retriever = RAGRetriever()
            embedder = retriever.get_embedder()
            embeddings = embedder.encode(chunk_texts, batch_size=8, show_progress_bar=True)

            dimension = embeddings.shape[1]
            index = faiss.IndexFlatL2(dimension)
            index.add(np.array(embeddings).astype('float32'))

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
            
        else:
            # ==========================================
            # 重载流式断点续传模式
            # ==========================================
            log_func(f"[WARN] 文件尺寸 ({file_size/1024/1024:.2f} MB) >= 10MB，为防止 OOM 崩溃，已切入重载流式微批次模式...")
            
            checkpoint_path = os.path.join(rag_db_dir, "checkpoint.json")
            start_offset = 0
            current_part = 1
            
            if os.path.exists(checkpoint_path):
                try:
                    with open(checkpoint_path, 'r', encoding='utf-8') as f:
                        cp = json.load(f)
                        start_offset = cp.get("offset", 0)
                        current_part = cp.get("part", 1)
                    log_func(f"[INFO] 检测到中断标记！将从游标位置 {start_offset} (文件分片 Part {current_part}) 处恢复处理，跳过已完成算力。")
                except Exception:
                    pass
            
            retriever = RAGRetriever()
            embedder = retriever.get_embedder()
            
            batch_texts = []
            batch_metadata = []
            last_offset = start_offset
            
            for block_text, offset in GlobalIndexerGUI.read_blocks_stream(original_path, start_offset):
                batch_texts.append(block_text)
                batch_metadata.append({
                    "text": block_text,
                    "metadata": {"chapter": f"Part {current_part}", "offset_marker": offset}
                })
                last_offset = offset
                
                # 达到 500 块执行强制微批次落盘与 GC 回收
                if len(batch_texts) >= 500:
                    log_func(f"-> 正在处理微批次 (Part {current_part})... 当前字节游标: {last_offset} / {file_size}")
                    embeddings = embedder.encode(batch_texts, batch_size=8, show_progress_bar=False)
                    
                    dimension = embeddings.shape[1]
                    part_index = faiss.IndexFlatL2(dimension)
                    part_index.add(np.array(embeddings).astype('float32'))
                    
                    # 保存临时碎片
                    faiss.write_index(part_index, os.path.join(rag_db_dir, f"part_{current_part}.index"))
                    with open(os.path.join(rag_db_dir, f"chunks_part_{current_part}.json"), 'w', encoding='utf-8') as f:
                        json.dump(batch_metadata, f, ensure_ascii=False, indent=2)
                        
                    # 更新断点标记
                    current_part += 1
                    with open(checkpoint_path, 'w', encoding='utf-8') as f:
                        json.dump({"offset": last_offset, "part": current_part}, f)
                        
                    # 绝对清理内存引用并强制 OS 回收
                    del embeddings
                    del part_index
                    del batch_texts
                    del batch_metadata
                    gc.collect()
                    
                    batch_texts = []
                    batch_metadata = []
            
            # 处理尾部不足 500 的余数碎块
            if batch_texts:
                log_func(f"-> 正在处理尾部微批次 (Part {current_part})...")
                embeddings = embedder.encode(batch_texts, batch_size=8, show_progress_bar=False)
                dimension = embeddings.shape[1]
                part_index = faiss.IndexFlatL2(dimension)
                part_index.add(np.array(embeddings).astype('float32'))
                
                faiss.write_index(part_index, os.path.join(rag_db_dir, f"part_{current_part}.index"))
                with open(os.path.join(rag_db_dir, f"chunks_part_{current_part}.json"), 'w', encoding='utf-8') as f:
                    json.dump(batch_metadata, f, ensure_ascii=False, indent=2)
                    
                del embeddings
                del part_index
                gc.collect()
            
            # 进入阶段四：碎片合并
            GlobalIndexerGUI.merge_index_parts(rag_db_dir, current_part, log_func)
            return True

def run_headless(target_file):
    success = GlobalIndexerGUI.run_indexing(target_file)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    safe_run_app(app_class=GlobalIndexerGUI, headless_func=run_headless, target_file="")