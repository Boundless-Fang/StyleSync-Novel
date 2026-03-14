import sys
import argparse
import os
import re
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from collections import Counter
import jieba
import jieba.posseg as pseg
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# 【关键配置】：强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# --- 物理目录对齐 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")

class LocalPlotCompressionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f4: 动态剧情切分与分层检索库构建 (纯本地降本版)")
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
        self.log("系统就绪。本环节采用正则表达式与本地 Jieba 提取，不消耗 API 额度。")

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
        """加载 f3a 提取的全局专属词库"""
        vocab_list = []
        if os.path.exists(vocab_path):
            try:
                with open(vocab_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(vocab_path, 'r', encoding='gbk') as f:
                    content = f.read()
            matches = re.findall(r'-\s*(.*?)[：:]', content)
            vocab_list = [m.strip() for m in matches if m.strip()]
        return vocab_list

    @staticmethod
    def extract_chunk_keywords(chunk_text, global_vocab, top_n=20):
        """交叉比对提取本块高频专属词"""
        keyword_counts = Counter()
        
        # 1. 优先扫描全局专属词
        for word in global_vocab:
            count = chunk_text.count(word)
            if count > 0:
                keyword_counts[word] += count
                
        # 2. 如果专属词命中太少，启动本地 Jieba 补充 (提取人名 nr, 地名 ns, 机构 nt)
        if len(keyword_counts) < top_n // 2:
            words = pseg.cut(chunk_text)
            for w, flag in words:
                if len(w) >= 2 and flag in ['nr', 'ns', 'nt']:
                    keyword_counts[w] += 1
                    
        # 返回最高频的前 N 个词
        return [word for word, count in keyword_counts.most_common(top_n)]

    @staticmethod
    def split_by_chapters(text, max_len=10000):
        """核心算法：通过正则提取章节，并根据字数动态打包"""
        # 匹配 "第X章" 或 "第X卷"
        pattern = r'\n(第[零一二三四五六七八九十百千万\d]+[章卷回节].*?)\n'
        segments = re.split(pattern, "\n" + text)
        
        chunks = []
        current_chunk_text = segments[0] if segments[0].strip() else ""
        current_titles = []
        
        for i in range(1, len(segments), 2):
            title = segments[i].strip()
            content = segments[i+1]
            
            # 追加到当前包
            current_titles.append(title)
            current_chunk_text += f"\n\n{title}\n{content}"
            
            # 达到字数阈值，切一刀
            if len(current_chunk_text) >= max_len:
                chunks.append({
                    "titles": current_titles,
                    "text": current_chunk_text.strip()
                })
                current_chunk_text = ""
                current_titles = []
                
        # 处理尾巴
        if current_chunk_text.strip():
            chunks.append({
                "titles": current_titles if current_titles else ["结尾部分"],
                "text": current_chunk_text.strip()
            })
            
        # 如果整本书没有匹配到任何章节(可能格式不对)，降级为纯字数硬切分
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
        
        target_dir = os.path.join(PROJ_DIR, project_name) if project_name else os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
        os.makedirs(target_dir, exist_ok=True)
        
        vocab_path = os.path.join(target_dir, "exclusive_vocab.md")
        rag_db_dir = os.path.join(target_dir, "hierarchical_rag_db")
        os.makedirs(rag_db_dir, exist_ok=True)
        
        faiss_index_path = os.path.join(rag_db_dir, "plot_summary.index")
        mapping_path = os.path.join(rag_db_dir, "summary_to_raw_mapping.json")
        outline_path = os.path.join(target_dir, "plot_outlines.md")

        try:
            try:
                with open(original_path, 'r', encoding='utf-8') as f:
                    full_text = f.read()
            except UnicodeDecodeError:
                with open(original_path, 'r', encoding='gbk') as f:
                    full_text = f.read()
        except Exception as e:
            log_func(f"❌ 读取原文失败: {e}")
            return False

        # 1. 加载全局专属词库
        global_vocab = LocalPlotCompressionApp.load_global_vocab(vocab_path)
        if not global_vocab:
            log_func("⚠️ 警告：未发现 f3a 专属词库，将完全依赖 Jieba 提取本章实体。")

        # 2. 动态章节切分
        log_func(f"正在进行智能章节切割与合并 (阈值: {chunk_size} 字)...")
        chunks_data = LocalPlotCompressionApp.split_by_chapters(full_text, max_len=chunk_size)
        total_chunks = len(chunks_data)
        log_func(f"原文已动态合并为 {total_chunks} 个叙事块。")

        # 3. 本地提取关键字与生成伪摘要
        log_func("正在本地扫描提取各模块高频核心实体...")
        summaries = []
        mapping_data = []
        
        with open(outline_path, 'w', encoding='utf-8') as f_out:
            f_out.write("# 核心事件与实体分布大纲 (本地伪摘要版)\n\n")
            
            for idx, item in enumerate(chunks_data):
                titles_str = "、".join(item["titles"])
                keywords = LocalPlotCompressionApp.extract_chunk_keywords(item["text"], global_vocab)
                keywords_str = "，".join(keywords)
                
                # 拼接伪摘要
                pseudo_summary = f"包含章节：{titles_str}\n本阶段出场核心实体/高频词：{keywords_str}"
                summaries.append(pseudo_summary)
                
                mapping_data.append({
                    "id": idx,
                    "summary": pseudo_summary,
                    "raw_chunk": item["text"]
                })
                
                # 记录落盘
                f_out.write(f"### 叙事块 {idx+1}\n{pseudo_summary}\n\n")

        # 4. 本地向量化并建立 FAISS 库
        log_func("实体提取完毕！正在将伪摘要向量化并构建 FAISS 检索库...")
        try:
            embedder = SentenceTransformer('shibing624/text2vec-base-chinese')
            summary_embeddings = embedder.encode(summaries, show_progress_bar=False)
            
            dimension = summary_embeddings.shape[1]
            index = faiss.IndexFlatL2(dimension)
            index.add(np.array(summary_embeddings).astype('float32'))
            
            faiss.write_index(index, faiss_index_path)
            with open(mapping_path, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, ensure_ascii=False, indent=2)
                
            log_func(f"✅ 纯本地分层检索库构建完成！全程 0 API 消耗。")
            return True
        except Exception as e:
            log_func(f"❌ 向量化或存储阶段失败: {str(e)}")
            return False

def run_headless(target_file, project_name=None):
    if os.path.isabs(target_file):
        original_path = target_file
    else:
        original_path = os.path.join(REFERENCE_DIR, target_file)
        
    if not os.path.exists(original_path):
        print(f"error: 未找到原文 {original_path}")
        sys.exit(1)
    
    print(f"开始静默执行本地章节合并与检索库构建: {original_path}")
    # 静默模式默认以 10000 字为打包阈值
    success = LocalPlotCompressionApp.execute_compression(original_path, 10000, print, project_name)
    if not success: sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, default="")
    parser.add_argument("--project", type=str, default="")
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        root = tk.Tk()
        app = LocalPlotCompressionApp(root)
        root.mainloop()
    else:
        if not args.target_file and unknown and not unknown[0].startswith('--'):
            args.target_file = unknown[0]
        run_headless(args.target_file, args.project)