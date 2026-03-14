import sys
import argparse
import os

# 【关键配置】：强制设置 HuggingFace 国内镜像源环境，确保模型稳定下载
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

class WorldviewApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f3b: 世界观整理与补全 (RAG 向量检索版)")
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
        
        self.btn_process = ttk.Button(self.root, text="▶ 全文定向检索与构建世界观", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=10, width=80, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。请确保已执行 f3a 生成专属词库，本环节将强依赖该词库进行 RAG 检索。")

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
            messagebox.showinfo("完成", "世界观设定构建完毕，文件已落盘。")
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
            
            # 确定读取与落盘的物理路径
            if project_name:
                target_dir = os.path.join(PROJ_DIR, project_name)
            else:
                target_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
            os.makedirs(target_dir, exist_ok=True)
            
            vocab_path = os.path.join(target_dir, "exclusive_vocab.md")
            save_path = os.path.join(target_dir, "world_settings.md")

            # 1. 强制读取 f3a 的专属词库与全量原文
            try:
                try:
                    with open(original_path, 'r', encoding='utf-8') as f:
                        full_text = f.read()
                except UnicodeDecodeError:
                    with open(original_path, 'r', encoding='gbk') as f:
                        full_text = f.read()
                
                vocab_text = ""
                query_keywords = []
                if os.path.exists(vocab_path):
                    try:
                        with open(vocab_path, 'r', encoding='utf-8') as f:
                            vocab_text = f.read()
                    except UnicodeDecodeError:
                        with open(vocab_path, 'r', encoding='gbk') as f:
                            vocab_text = f.read()
                    # 使用正则提取专属词库中 "-" 后和 "：" 前的具体名词作为检索探针
                    # 例如：从 "- 降龙十八掌：丐帮绝学" 中提取出 "降龙十八掌"
                    matches = re.findall(r'-\s*(.*?)[：:]', vocab_text)
                    query_keywords = [m.strip() for m in matches if m.strip()]
                    
                    if not query_keywords:
                        log_func("警告：专属词库存在，但未能提取出有效探针，可能格式有误。")
                else:
                    log_func("❌ 致命错误：未找到专属词库 (exclusive_vocab.md)。请先执行 f3a！")
                    return False
            except Exception as e:
                log_func(f"读取文件失败: {e}")
                return False

            # 2. 文本分块与向量化 (RAG 核心逻辑)
            log_func("正在进行全量文本分块与本地向量化计算...")
            try:
                embedder = SentenceTransformer('shibing624/text2vec-base-chinese')
                chunks = WorldviewApp.chunk_text(full_text)
                log_func(f"全文切分为 {len(chunks)} 个文本块。正在生成向量库...")
                
                chunk_embeddings = embedder.encode(chunks, show_progress_bar=False)
                
                dimension = chunk_embeddings.shape[1]
                index = faiss.IndexFlatL2(dimension)
                index.add(np.array(chunk_embeddings).astype('float32'))
                
                # 3. 利用 f3a 的专属名词作为探针进行精准检索
                log_func(f"正在使用 {len(query_keywords)} 个专属名词检索核心设定片段...")
                retrieved_chunks = set()
                
                # 引入额外的世界观高维引导词，强行逼迫 RAG 抓取底层规则
                meta_queries = ["境界 突破 修炼 功法", "版图 国家 大陆 势力", "历史 传说 宗门 战争"]
                all_queries = meta_queries + query_keywords
                
                # 批量查询提升速度
                for i in range(0, len(all_queries), 5):
                    batch_queries = [" ".join(all_queries[i:i+5])]
                    query_vec = embedder.encode(batch_queries)
                    distances, indices = index.search(np.array(query_vec).astype('float32'), k=6) 
                    for idx in indices[0]:
                        if idx != -1:
                            retrieved_chunks.add(chunks[idx])
                
                # 拼接召回的上下文 (控制在安全 Token 范围内)
                context_text = "\n...\n".join(list(retrieved_chunks)[:40])
                log_func(f"成功召回 {len(retrieved_chunks)} 个强相关设定片段，即将请求大模型。")
                
            except Exception as e:
                log_func(f"❌ 向量化或检索失败: {str(e)}")
                return False

            # 4. 请求大语言模型构建世界观
            log_func("正在调用大模型重组世界观设定...")
            prompt_header = """【系统指令】：
请基于提供的“文本高相关度片段”及参考的“专属词库”，构建并补全该小说的世界观设定。
请提取确切的事实与设定，严禁罗列剧情流水账。必须使用 Markdown 结构输出以下 4 个固定板块：
世界观（仙侠/西幻/古代/近代/都市/都市奇谭/未来/末世等）：
类型（热血/冷酷/温馨/真实等）：
女主数量（无女主/单女主/多女主）：
核心爽点/金手指：
出场角色以及别名（没有别名就不要用括号）：角色一（别名一、别名二...）、角色二（别名一、别名二...）...
力量体系（如境界、功法、体质）：
种族/阵营（以及每个实体简要说明）：
历史/传说：
资源：
其他：

如果文本中存在信息断层，请基于现有逻辑进行合理、客观的推演补全，并在补全项后强制标注“（推演补全）”。

【专属词库参考】：
"""
            prompt = prompt_header + vocab_text + "\n\n【文本高相关度片段 (经 RAG 检索提取)】：\n" + context_text

            api_key = os.getenv("DEEPSEEK_API_KEY")
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个严谨的设定整理专家。只允许输出 Markdown 格式的纯文本，禁止输出多余的寒暄语。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.4 # 允许适度推演
            }
            
            try:
                response = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=180)
                response.raise_for_status()
                result_text = response.json()['choices'][0]['message']['content'].strip()
                
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(result_text)
                log_func(f"✅ 世界观构建完成！文件落盘至: {save_path}")
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
    
    print(f"开始静默执行 RAG 构建世界观: {original_path}")
    success = WorldviewApp.execute_extraction(original_path, model, print, project_name)
    if not success: sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, default="")
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        root = tk.Tk()
        app = WorldviewApp(root)
        root.mainloop()
    else:
        if not args.target_file and unknown and not unknown[0].startswith('--'):
            args.target_file = unknown[0]
        run_headless(args.target_file, args.project, args.model)