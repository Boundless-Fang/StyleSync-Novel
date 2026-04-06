import os
import json
import argparse
import threading
import faiss
import numpy as np

# =====================================================================
# 1. 跨目录寻址：将父目录加入环境变量
# =====================================================================
import sys
from core._core_gui_runner import safe_run_app

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    tk = None
    ttk = None

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# =====================================================================
# 2. 导入 core 模块
# =====================================================================
from core._core_config import PROJ_DIR
from core._core_utils import smart_read_text, atomic_write
from core._core_rag import RAGRetriever

class ProjectContextIndexerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f4c: 动态工程上下文检索库构建 (已生成正文 RAG)")
        self.root.geometry("600x350")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        frame_base = ttk.LabelFrame(self.root, text="1. 定位当前创作工程")
        frame_base.pack(fill="x", **padding)
        
        ttk.Label(frame_base, text="目标项目名:").grid(row=0, column=0, sticky="w", padx=5, pady=10)
        self.project_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.project_var, width=40).grid(row=0, column=1, sticky="w", padx=5)

        self.btn_process = ttk.Button(self.root, text="同步并构建项目上下文向量库", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=10, width=75, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。本节点负责将项目已生成的正文同步至本地 RAG 数据库，防止大模型剧情失忆。")

    def log(self, message):
        if not tk: return
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def start_process_thread(self):
        project_name = self.project_var.get().strip()
        if not project_name:
            messagebox.showwarning("提示", "项目名称为必填项！")
            return
            
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, args=(project_name,), daemon=True).start()

    def process_logic(self, project_name):
        result = self.execute_indexing(project_name, self.log)
        if result and tk:
            messagebox.showinfo("完成", f"【{project_name}】上下文向量库更新完毕！")
        self.btn_process.config(state="normal")

    @staticmethod
    def chunk_text(text, max_len=800):
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        chunks, current_chunk = [], ""
        for p in paragraphs:
            if len(current_chunk) + len(p) <= max_len:
                current_chunk += p + "\n"
            else:
                if current_chunk: chunks.append(current_chunk.strip())
                current_chunk = p + "\n"
        if current_chunk: chunks.append(current_chunk.strip())
        return chunks

    @staticmethod
    def execute_indexing(project_name, log_func):
        target_dir = os.path.join(PROJ_DIR, project_name)
        if not os.path.exists(target_dir):
            log_func(f"[ERROR] 未找到工程目录: {target_dir}")
            return False

        content_dir = os.path.join(target_dir, "content")
        if not os.path.exists(content_dir):
            log_func(f"[WARN] 内容目录不存在，当前项目暂无正文需要索引。")
            return True

        # 读取所有章节并排序，确保逻辑连贯
        chapter_files = sorted([f for f in os.listdir(content_dir) if f.endswith(".txt")])
        if not chapter_files:
            log_func("[INFO] 尚未生成任何小说正文，跳过构建。")
            return True

        log_func(f"正在读取 {len(chapter_files)} 章历史正文数据...")
        all_chunks = []
        for f_name in chapter_files:
            content = smart_read_text(os.path.join(content_dir, f_name))
            if content:
                # 切块并携带章节元数据
                blocks = ProjectContextIndexerApp.chunk_text(content, max_len=1000)
                for block in blocks:
                    all_chunks.append({
                        "text": f"[{f_name.replace('.txt', '')}] {block}",
                        "raw_chunk": block
                    })

        if not all_chunks:
            log_func("[WARN] 提取到的有效文本块为空。")
            return True

        log_func(f"原文已切分为 {len(all_chunks)} 个上下文碎块，开始调用核心层进行向量化...")
        
        context_db_dir = os.path.join(target_dir, "context_rag_db")
        os.makedirs(context_db_dir, exist_ok=True)
        index_path = os.path.join(context_db_dir, "vector.index")
        chunks_path = os.path.join(context_db_dir, "chunks.json")

        try:
            retriever = RAGRetriever()
            embedder = retriever.get_embedder()
            
            chunk_texts = [item["text"] for item in all_chunks]
            embeddings = embedder.encode(chunk_texts, batch_size=8, show_progress_bar=False)
            
            dimension = embeddings.shape[1]
            index = faiss.IndexFlatL2(dimension)
            index.add(np.array(embeddings).astype('float32'))
            
            # 安全原子落盘
            try:
                atomic_write(index_path, index, data_type='faiss')
                atomic_write(chunks_path, all_chunks, data_type='json')
            except Exception as e:
                log_func(f"[ERROR] 向量库落盘失败: {e}")
                return False
                
            log_func(f"[INFO] 动态上下文向量库构建成功！落盘至: {context_db_dir}")
            return True
            
        except Exception as e:
            log_func(f"[ERROR] 向量化构建发生严重异常: {e}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(project_name=""):
    import sys
    if not project_name:
        sys.exit(1)
        
    print(f"开始静默执行工程上下文 RAG 构建: [{project_name}]")
    success = ProjectContextIndexerApp.execute_indexing(project_name, print)
    if not success: sys.exit(1)

if __name__ == "__main__":
    safe_run_app(
        app_class=ProjectContextIndexerApp,
        headless_func=run_headless,
        project_name=""
    )