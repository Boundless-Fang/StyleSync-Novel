import sys
import argparse
import os

# 【关键配置】：在导入模型库之前，强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import requests
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from dotenv import load_dotenv
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import re

load_dotenv()

# --- 物理目录对齐 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")

class ExclusiveVocabApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f3a: 专属词库提取 (RAG 向量检索版)")
        self.root.geometry("650x450")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        frame_original = ttk.LabelFrame(self.root, text="1. 选择小说原文 (.txt)")
        frame_original.pack(fill="x", **padding)
        self.original_var = tk.StringVar()
        ttk.Entry(frame_original, textvariable=self.original_var, state="readonly", width=60).grid(row=0, column=0, padx=5, pady=10)
        ttk.Button(frame_original, text="浏览...", command=self.select_original).grid(row=0, column=1, padx=5, pady=10)

        frame_model = ttk.LabelFrame(self.root, text="2. 选择处理模型")
        frame_model.pack(fill="x", **padding)
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Radiobutton(frame_model, text="DeepSeek V3 (标准)", variable=self.model_var, value="deepseek-chat").pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Radiobutton(frame_model, text="DeepSeek R1 (推理)", variable=self.model_var, value="deepseek-reasoner").pack(side=tk.LEFT, padx=10, pady=5)
        
        self.btn_process = ttk.Button(self.root, text="▶ 全文向量化与提取专属词库", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=10, width=80, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。已配置默认国内镜像源。首次运行将自动下载本地 Embedding 模型。")

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def select_original(self):
        init_dir = REFERENCE_DIR if os.path.exists(REFERENCE_DIR) else BASE_DIR
        path = filedialog.askopenfilename(initialdir=init_dir, title="选择原文", filetypes=[("Text Files", "*.txt")])
        if path: self.original_var.set(path)

    def start_process_thread(self):
        if not self.original_var.get():
            messagebox.showwarning("提示", "请先选择原文文件！")
            return
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, daemon=True).start()

    def process_logic(self):
        original_path = self.original_var.get()
        model = self.model_var.get()
        result = self.execute_extraction(original_path, model, self.log, project_name=None)
        if result:
            messagebox.showinfo("完成", "专属词库提取完毕，文件已落盘。")
        self.btn_process.config(state="normal")

    @staticmethod
    def chunk_text(text, max_len=600):
        """将全量文本按照段落切分为固定长度的文本块"""
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        chunks = []
        current_chunk = ""
        for p in paragraphs:
            if len(current_chunk) + len(p) <= max_len:
                current_chunk += p + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = p + "\n"
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    @staticmethod
    def execute_extraction(original_path, model, log_func, project_name=None):
        try:
            novel_name = os.path.splitext(os.path.basename(original_path))[0]
            words_path = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "statistics", "高频词.txt")

            # 1. 读取全量文件与高频词
            try:
                try:
                    with open(original_path, 'r', encoding='utf-8') as f:
                        full_text = f.read()
                except UnicodeDecodeError:
                    with open(original_path, 'r', encoding='gbk') as f:
                        full_text = f.read()
                
                words_text = ""
                query_keywords = []
                if os.path.exists(words_path):
                    try:
                        with open(words_path, 'r', encoding='utf-8') as f:
                            words_text = f.read()
                    except UnicodeDecodeError:
                        with open(words_path, 'r', encoding='gbk') as f:
                            words_text = f.read()
                    # 提取高频词列表中括号前的内容作为检索词汇
                    matches = re.findall(r'(\S+)\(\d+\)', words_text)
                    query_keywords = matches[:100] # 取前100个高频词作为RAG检索的锚点
                else:
                    log_func("警告：未找到本地高频词文件，无法进行精准 RAG 检索。")
                    return False
            except Exception as e:
                log_func(f"读取文件失败: {e}")
                return False

            if project_name:
                target_dir = os.path.join(PROJ_DIR, project_name)
            else:
                target_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
            os.makedirs(target_dir, exist_ok=True)
            save_path = os.path.join(target_dir, "exclusive_vocab.md")

            # 2. 文本分块与向量化 (RAG 核心逻辑)
            log_func("正在进行全量文本分块与本地向量化计算...")
            try:
                # 加载轻量级中文 Embedding 模型 (会自动从配置的镜像源拉取)
                embedder = SentenceTransformer('shibing624/text2vec-base-chinese')
                
                chunks = ExclusiveVocabApp.chunk_text(full_text)
                log_func(f"全文切分为 {len(chunks)} 个文本块。正在生成向量库...")
                
                chunk_embeddings = embedder.encode(chunks, show_progress_bar=False)
                
                # 构建 FAISS 索引
                dimension = chunk_embeddings.shape[1]
                index = faiss.IndexFlatL2(dimension)
                index.add(np.array(chunk_embeddings).astype('float32'))
                
                # 3. 根据高频词进行检索
                log_func("正在检索与高频词关联的上下文文本块...")
                retrieved_chunks = set()
                
                # 将高频词分为 10 组进行批查询以加快速度
                for i in range(0, len(query_keywords), 10):
                    batch_queries = [" ".join(query_keywords[i:i+10])]
                    query_vec = embedder.encode(batch_queries)
                    distances, indices = index.search(np.array(query_vec).astype('float32'), k=5) # 每组查询取最相关的前5个块
                    for idx in indices[0]:
                        if idx != -1:
                            retrieved_chunks.add(chunks[idx])
                
                # 拼接召回的上下文
                context_text = "\n...\n".join(list(retrieved_chunks)[:30]) # 限制最终提交给 LLM 的块数量，控制在安全 Token 范围内
                log_func(f"成功召回 {len(retrieved_chunks)} 个高相关度片段，即将请求大模型。")
                
            except Exception as e:
                log_func(f"❌ 向量化或检索失败: {str(e)}")
                return False

            # 4. 请求大语言模型
            prompt_header = """按照以下格式整理该文本的专属词汇库
角色名字
力量体系（如境界、功法、体质）
种族/阵营
地点
资源
其他

【高频词参考】：
"""
            prompt = prompt_header + words_text + "\n\n【文本高相关度片段】：\n" + context_text

            api_key = os.getenv("DEEPSEEK_API_KEY")
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个严谨的信息提取助手。只允许输出 Markdown 格式的纯文本列表。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2
            }
            
            try:
                response = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=180)
                response.raise_for_status()
                result_text = response.json()['choices'][0]['message']['content'].strip()
                
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(result_text)
                log_func(f"✅ 提取完成！文件落盘至: {save_path}")
                return True
            except Exception as e:
                log_func(f"❌ API 调用失败: {str(e)}")
                return False
        except Exception as e:
            log_func(f"❌ 分析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(target_file, project_name=None, model="deepseek-chat"):
    if os.path.isabs(target_file):
        original_path = target_file
    else:
        original_path = os.path.join(REFERENCE_DIR, target_file)
        
    if not os.path.exists(original_path):
        print(f"error: 未找到原文 {original_path}")
        sys.exit(1)
    
    print(f"开始静默执行 RAG 专属词库提取: {original_path}")
    success = ExclusiveVocabApp.execute_extraction(original_path, model, print, project_name)
    if not success: sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, default="")
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        root = tk.Tk()
        app = ExclusiveVocabApp(root)
        root.mainloop()
    else:
        if not args.target_file and unknown and not unknown[0].startswith('--'):
            args.target_file = unknown[0]
        run_headless(args.target_file, args.project, args.model)