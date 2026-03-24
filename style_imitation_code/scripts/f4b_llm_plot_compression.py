import os
import re
import json
import argparse
import threading
from collections import Counter
import jieba
import jieba.posseg as pseg
import faiss
import numpy as np

# =====================================================================
# 1. 跨目录寻址：将父目录(style_imitation_code)加入环境变量
# =====================================================================
import sys
current_dir = os.path.dirname(os.path.abspath(__file__)) # 指向 scripts/
parent_dir = os.path.dirname(current_dir)                # 指向 style_imitation_code/
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# =====================================================================
# 2. 导入 core 模块 (注意加 core. 前缀)
# =====================================================================
from core._core_config import BASE_DIR, PROJECT_ROOT, REFERENCE_DIR, STYLE_DIR, PROJ_DIR
from core._core_utils import smart_read_text
from core._core_rag import RAGRetriever

class LocalPlotCompressionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f4b: 动态剧情切分与分层检索库构建 (纯本地降本版)")
        self.root.geometry("680x420")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        frame_original = ttk.LabelFrame(self.root, text="1. 选择小说原文 (.txt)")
        frame_original.pack(fill="x", **padding)
        self.original_var = tk.StringVar()
        ttk.Entry(frame_original, textvariable=self.original_var, state="readonly", width=65).grid(row=0, column=0, padx=5, pady=10)
        ttk.Button(frame_original, text="浏览...", command=self.select_original).grid(row=0, column=1, padx=5, pady=10)

        frame_settings = ttk.LabelFrame(self.root, text="2. 切分与提取策略 (纯本地，0 API 消耗)")
        frame_settings.pack(fill="x", **padding)
        ttk.Label(frame_settings, text="打包阈值(字数):").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.chunk_size_var = tk.IntVar(value=10000)
        ttk.Entry(frame_settings, textvariable=self.chunk_size_var, width=15).grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(frame_settings, text="*系统将动态合并章节，超过此字数即切分打包", foreground="gray").grid(row=0, column=2, sticky="w", padx=10)
        
        self.btn_process = ttk.Button(self.root, text="▶ 执行章节切分与构建本地检索库", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=10, width=85, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。本环节将采用统一的 1024 维 BAAI 模型构建同人库。")

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def select_original(self):
        init_dir = REFERENCE_DIR if os.path.exists(REFERENCE_DIR) else BASE_DIR
        path = filedialog.askopenfilename(initialdir=init_dir, filetypes=[("Text Files", "*.txt")])
        if path: self.original_var.set(path)

    def start_process_thread(self):
        if not self.original_var.get():
            messagebox.showwarning("提示", "请先选择原文文件！")
            return
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, daemon=True).start()

    def process_logic(self):
        original_path = self.original_var.get()
        chunk_size = self.chunk_size_var.get()
        result = self.execute_compression(original_path, chunk_size, self.log, project_name=None)
        if result:
            messagebox.showinfo("完成", "本地动态分层检索数据库建立完毕！")
        self.btn_process.config(state="normal")

    @staticmethod
    def load_global_vocab(vocab_path):
        vocab_list = []
        if os.path.exists(vocab_path):
            content = smart_read_text(vocab_path)
            matches = re.findall(r'-\s*(.*?)[：:]', content)
            vocab_list = [m.strip() for m in matches if m.strip()]
        return vocab_list

    @staticmethod
    def extract_chunk_keywords(chunk_text, global_vocab, top_n=20):
        keyword_counts = Counter()
        for word in global_vocab:
            count = chunk_text.count(word)
            if count > 0:
                keyword_counts[word] += count
                
        if len(keyword_counts) < top_n // 2:
            words = pseg.cut(chunk_text)
            for w, flag in words:
                if len(w) >= 2 and flag in ['nr', 'ns', 'nt']:
                    keyword_counts[w] += 1
                    
        return [word for word, count in keyword_counts.most_common(top_n)]

    @staticmethod
    def split_by_chapters(text, max_len=10000):
        pattern = r'\n(第[零一二三四五六七八九十百千万\d]+[章卷回节].*?)\n'
        segments = re.split(pattern, "\n" + text)
        
        chunks = []
        current_chunk_text = segments[0] if segments[0].strip() else ""
        current_titles = []
        
        for i in range(1, len(segments), 2):
            title = segments[i].strip()
            content = segments[i+1]
            
            current_titles.append(title)
            current_chunk_text += f"\n\n{title}\n{content}"
            
            if len(current_chunk_text) >= max_len:
                chunks.append({
                    "titles": current_titles,
                    "text": current_chunk_text.strip()
                })
                current_chunk_text = ""
                current_titles = []
                
        if current_chunk_text.strip():
            chunks.append({
                "titles": current_titles if current_titles else ["结尾部分"],
                "text": current_chunk_text.strip()
            })
            
        if not chunks:
            paragraphs = text.split('\n')
            temp_text = ""
            for p in paragraphs:
                temp_text += p + "\n"
                if len(temp_text) >= max_len:
                    chunks.append({"titles": ["无章节片段"], "text": temp_text.strip()})
                    temp_text = ""
            if temp_text.strip():
                chunks.append({"titles": ["无章节片段"], "text": temp_text.strip()})
                
        return chunks

    @staticmethod
    def execute_compression(original_path, chunk_size, log_func, project_name=None):
        novel_name = os.path.splitext(os.path.basename(original_path))[0]
        style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
        os.makedirs(style_dir, exist_ok=True)
        
        vocab_path = os.path.join(style_dir, "exclusive_vocab.md")
        rag_db_dir = os.path.join(style_dir, "hierarchical_rag_db")
        os.makedirs(rag_db_dir, exist_ok=True)
        
        faiss_index_path = os.path.join(rag_db_dir, "plot_summary.index")
        mapping_path = os.path.join(rag_db_dir, "summary_to_raw_mapping.json")
        outline_path = os.path.join(style_dir, "plot_outlines.md")
        
        project_dir = None
        if project_name:
            project_dir = os.path.join(PROJ_DIR, project_name)
            os.makedirs(project_dir, exist_ok=True)

        try:
            full_text = smart_read_text(original_path)
        except Exception as e:
            log_func(f"❌ 读取原文失败: {e}")
            return False

        global_vocab = LocalPlotCompressionApp.load_global_vocab(vocab_path)
        if not global_vocab:
            log_func("⚠️ 警告：未发现 f3a 专属词库，将完全依赖 Jieba 提取本章实体。")

        log_func(f"正在进行智能章节切割与合并 (阈值: {chunk_size} 字)...")
        chunks_data = LocalPlotCompressionApp.split_by_chapters(full_text, max_len=chunk_size)
        total_chunks = len(chunks_data)
        log_func(f"原文已动态合并为 {total_chunks} 个叙事块。")

        log_func("正在本地扫描提取各模块高频核心实体...")
        summaries = []
        mapping_data = []
        
        with open(outline_path, 'w', encoding='utf-8') as f_out:
            f_out.write("# 核心事件与实体分布大纲 (本地伪摘要版)\n\n")
            
            for idx, item in enumerate(chunks_data):
                titles_str = "、".join(item["titles"])
                keywords = LocalPlotCompressionApp.extract_chunk_keywords(item["text"], global_vocab)
                keywords_str = "，".join(keywords)
                
                pseudo_summary = f"包含章节：{titles_str}\n本阶段出场核心实体/高频词：{keywords_str}"
                summaries.append(pseudo_summary)
                
                mapping_data.append({
                    "id": idx,
                    "summary": pseudo_summary,
                    "raw_chunk": item["text"]
                })
                
                f_out.write(f"### 叙事块 {idx+1}\n{pseudo_summary}\n\n")

        log_func("实体提取完毕！正在通过 _core_rag 加载 BAAI 模型进行向量化...")
        try:
            # 统一通过 Retriever 获取底层的 1024 维 BAAI 编码器
            retriever = RAGRetriever()
            embedder = retriever.get_embedder()
            
            # 使用获取到的模型进行批量编码
            summary_embeddings = embedder.encode(summaries, show_progress_bar=False)
            dimension = summary_embeddings.shape[1]
            index = faiss.IndexFlatL2(dimension)
            index.add(np.array(summary_embeddings).astype('float32'))
            
            import shutil
            temp_write_path = "temp_write_index.bin"
            faiss.write_index(index, temp_write_path)
            shutil.move(temp_write_path, faiss_index_path)
            
            with open(mapping_path, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, ensure_ascii=False, indent=2)
                
            msg = f"✅ 纯本地分层检索库构建完成！全程 0 API 消耗。\n文件已落盘至: {style_dir}"
            
            if project_dir:
                p_outline = os.path.join(project_dir, "plot_outlines.md")
                shutil.copy2(outline_path, p_outline)
                
                p_rag_dir = os.path.join(project_dir, "hierarchical_rag_db")
                if os.path.exists(p_rag_dir):
                    shutil.rmtree(p_rag_dir)
                shutil.copytree(rag_db_dir, p_rag_dir)
                
                msg += f"\n已同步大纲与检索库至项目目录: {project_dir}"
                
            log_func(msg)
            return True
        except Exception as e:
            log_func(f"❌ 向量化或存储阶段失败: {str(e)}")
            return False

def run_headless(target_file, project_name=None):
    import sys
    if os.path.isabs(target_file):
        original_path = target_file
    else:
        original_path = os.path.join(REFERENCE_DIR, target_file)
        
    if not os.path.exists(original_path):
        print(f"error: 未找到原文 {original_path}")
        sys.exit(1)
    
    print(f"开始静默执行本地章节合并与检索库构建: {original_path}")
    success = LocalPlotCompressionApp.execute_compression(original_path, 10000, print, project_name)
    if not success: sys.exit(1)

if __name__ == "__main__":
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, default="")
    parser.add_argument("--project", type=str, default="")
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        root = tk.Tk()
        app = LocalPlotCompressionApp(root)
        root.mainloop()
    else:
        if not args.target_file and unknown and not unknown[0].startswith('--'):
            args.target_file = unknown[0]
        run_headless(args.target_file, args.project)