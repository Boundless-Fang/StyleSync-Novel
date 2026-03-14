import sys
import argparse
import os
import requests
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from dotenv import load_dotenv
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import json

# 【关键配置】：强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
load_dotenv()

# --- 物理目录对齐 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")

class NovelGenerationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f5b: 大模型正文流式生成引擎 (双分支版)")
        self.root.geometry("750x680")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        # 1. 项目与章节基础信息
        frame_base = ttk.LabelFrame(self.root, text="1. 目标定位 (请确保 f5a 已生成大纲)")
        frame_base.pack(fill="x", **padding)
        
        ttk.Label(frame_base, text="目标项目名:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.project_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.project_var, width=25).grid(row=0, column=1, sticky="w", padx=5)
        
        ttk.Label(frame_base, text="本章章节名:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.chapter_name_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.chapter_name_var, width=25).grid(row=1, column=1, sticky="w", padx=5)

        # 2. 模型与控制参数
        frame_model = ttk.LabelFrame(self.root, text="2. 生成参数与创作分支")
        frame_model.pack(fill="x", **padding)
        
        # 创作分支选择
        ttk.Label(frame_model, text="创作模式:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.branch_var = tk.StringVar(value="同人创作")
        ttk.Radiobutton(frame_model, text="同人创作 (检索原著设定)", variable=self.branch_var, value="同人创作").grid(row=0, column=1, sticky="w", padx=10)
        ttk.Radiobutton(frame_model, text="完全原创 (检索前文记录)", variable=self.branch_var, value="完全原创").grid(row=0, column=2, sticky="w", padx=10)

        # 模型选择
        ttk.Label(frame_model, text="推理模型:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Radiobutton(frame_model, text="DeepSeek V3 (标准)", variable=self.model_var, value="deepseek-chat").grid(row=1, column=1, sticky="w", padx=10)
        ttk.Radiobutton(frame_model, text="DeepSeek R1 (推理)", variable=self.model_var, value="deepseek-reasoner").grid(row=1, column=2, sticky="w", padx=10)
        
        self.btn_process = ttk.Button(self.root, text="▶ 执行正文流式生成", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=15, width=95, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 10))
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。正在等待流式数据...")

    def log(self, message, append=False):
        self.log_text.config(state="normal")
        if append:
            self.log_text.insert(tk.END, message)
        else:
            self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def start_process_thread(self):
        project_name = self.project_var.get().strip()
        chapter_name = self.chapter_name_var.get().strip()
        
        if not project_name or not chapter_name:
            messagebox.showwarning("提示", "项目名和章节名为必填项！")
            return
            
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, args=(project_name, chapter_name), daemon=True).start()

    def process_logic(self, project_name, chapter_name):
        model = self.model_var.get()
        branch = self.branch_var.get()
        self.execute_generation(project_name, chapter_name, model, branch, self.log)
        self.btn_process.config(state="normal")

    @staticmethod
    def read_file_safe(filepath, max_len=None):
        """安全读取文件，如果不存在返回空字符串"""
        if os.path.exists(filepath):
            try:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        return content[:max_len] if max_len else content
                except UnicodeDecodeError:
                    with open(filepath, 'r', encoding='gbk') as f:
                        content = f.read()
                        return content[:max_len] if max_len else content
            except Exception:
                return ""
        return ""

    @staticmethod
    def chunk_text(text, max_len=600):
        """动态分块函数，用于原创分支的前文处理"""
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
    def load_all_characters(target_dir):
        """遍历读取所有角色卡"""
        char_dir = os.path.join(target_dir, "character_profiles")
        if not os.path.exists(char_dir):
            return "无角色卡数据。"
        
        char_texts = []
        for filename in os.listdir(char_dir):
            if filename.endswith(".md"):
                char_texts.append(NovelGenerationApp.read_file_safe(os.path.join(char_dir, filename)))
        return "\n\n".join(char_texts) if char_texts else "无角色卡数据。"

    @staticmethod
    def get_previous_context(content_dir, current_chapter_name):
        """自动寻址并读取上一章末尾，用于无缝衔接"""
        if not os.path.exists(content_dir):
            return "无前文。"
            
        chapters = [f for f in os.listdir(content_dir) if f.endswith(".txt")]
        if not chapters:
            return "无前文。"
            
        chapters_paths = [os.path.join(content_dir, f) for f in chapters if f != f"{current_chapter_name}.txt"]
        if not chapters_paths:
            return "无前文。"
            
        chapters_paths.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        last_chapter_path = chapters_paths[0]
        
        content = NovelGenerationApp.read_file_safe(last_chapter_path)
        return content[-1000:] if len(content) > 1000 else content

    @staticmethod
    def execute_generation(project_name, chapter_name, model, branch, log_func):
        target_dir = os.path.join(PROJ_DIR, project_name)
        if not os.path.exists(target_dir):
            log_func(f"❌ 错误: 未找到项目目录 {target_dir}")
            return False

        outline_path = os.path.join(target_dir, "chapter_structures", f"{chapter_name}_outline.md")
        chapter_outline = NovelGenerationApp.read_file_safe(outline_path)
        if not chapter_outline:
            log_func(f"❌ 错误: 未找到本章大纲文件 {outline_path}，请先执行 f5a。")
            return False

        # --- 1. 组装 System Prompt ---
        log_func(f"当前创作模式: 【{branch}】。正在加载特征库...")
        features = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "features.md"))
        worldview = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "world_settings.md"))
        positive_words = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "positive_words.md"))
        negative_words = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "negative_words.md"))
        
        # 原创分支不一定加载全量角色卡，但在此作为统一的基础环境设定输入
        characters = NovelGenerationApp.load_all_characters(target_dir)

        system_prompt_header = """你是一个顶尖的网络小说作家，拥有极强的画面感塑造与剧情推动能力。
【最高权重后台指令】：以下提供的[文风特征]、[世界观设定]、[角色卡]仅为你的底层逻辑限制。绝对禁止在正文叙述中直接陈述、概括、罗列或背诵这些属性文档！你必须将这些设定化为无形的动作、细节、环境描写和对话自然展现。

【底层约束库】：
[文风与写法特征限制]
"""
        system_prompt = system_prompt_header + features + "\n\n[正向词汇偏好] (请在行文中尽量自然使用)\n" + positive_words + "\n\n[负向禁用词汇] (绝对禁止使用以下词汇)\n" + negative_words + "\n\n[全局世界观与力量体系]\n" + worldview + "\n\n[核心角色状态字典]\n" + characters + "\n"

        # --- 2. 组装 User Prompt ---
        log_func("正在提取上下文接榫点与动态关联数据...")
        content_dir = os.path.join(target_dir, "content")
        os.makedirs(content_dir, exist_ok=True)
        previous_context = NovelGenerationApp.get_previous_context(content_dir, chapter_name)

        # 核心分支隔离逻辑：检索不同的 RAG 数据源
        rag_context = "无历史剧情记录。"
        embedder = None
        
        try:
            embedder = SentenceTransformer('shibing624/text2vec-base-chinese')
            query_vec = embedder.encode([chapter_outline[:600]]) # 用本章大纲作为查询探针
            
            if branch == "同人创作":
                log_func("触发同人创作分支：向原著提取的高阶 RAG 数据库发起检索...")
                rag_db_dir = os.path.join(target_dir, "hierarchical_rag_db")
                faiss_index_path = os.path.join(rag_db_dir, "plot_summary.index")
                mapping_path = os.path.join(rag_db_dir, "summary_to_raw_mapping.json")
                
                if os.path.exists(faiss_index_path) and os.path.exists(mapping_path):
                    index = faiss.read_index(faiss_index_path)
                    try:
                        with open(mapping_path, 'r', encoding='utf-8') as f:
                            mapping_data = json.load(f)
                    except UnicodeDecodeError:
                        with open(mapping_path, 'r', encoding='gbk') as f:
                            mapping_data = json.load(f)
                    
                    distances, indices = index.search(np.array(query_vec).astype('float32'), k=2) 
                    retrieved_summaries = [mapping_data[idx]["summary"] for idx in indices[0] if idx != -1 and idx < len(mapping_data)]
                    if retrieved_summaries:
                        rag_context = "\n\n".join(retrieved_summaries)
                        log_func("已成功召回原著中的关联设定。")

            elif branch == "完全原创":
                log_func("触发完全原创分支：读取现有生成章节进行内存向量化匹配...")
                past_texts = []
                for f_name in sorted(os.listdir(content_dir), key=lambda x: os.path.getmtime(os.path.join(content_dir, x))):
                    if f_name.endswith(".txt") and f_name != f"{chapter_name}.txt":
                        past_texts.append(NovelGenerationApp.read_file_safe(os.path.join(content_dir, f_name)))
                
                full_past_text = "\n".join(past_texts)
                if full_past_text.strip():
                    chunks = NovelGenerationApp.chunk_text(full_past_text, max_len=800)
                    if chunks:
                        chunk_embeddings = embedder.encode(chunks, show_progress_bar=False)
                        index = faiss.IndexFlatL2(chunk_embeddings.shape[1])
                        index.add(np.array(chunk_embeddings).astype('float32'))
                        
                        distances, indices = index.search(np.array(query_vec).astype('float32'), k=3)
                        retrieved_chunks = [chunks[idx] for idx in indices[0] if idx != -1 and idx < len(chunks)]
                        rag_context = "\n\n...\n\n".join(retrieved_chunks)
                        log_func(f"已成功召回 {len(retrieved_chunks)} 个由系统生成的前置章节高相关文本块。")
                else:
                    log_func("尚未生成前置章节，无法构建原创约束。")
        except Exception as e:
            log_func(f"⚠️ RAG 检索异常 (将降级为无 RAG 约束模式): {e}")

        user_prompt_header = """【前文回顾】（请紧承接以下段落的物理动作或对话，无缝衔接）：
"""
        user_prompt_mid = """

【关联历史剧情记录】（用于辅助参考因果关系）：
"""
        user_prompt_end = """

【本章详细大纲】（本章必须严格执行以下大纲内容，禁止自行跳跃剧情或直接概括）：
"""
        user_prompt_footer = """

【写作要求】：
1. 立即开始输出本章正文内容，不需要任何寒暄、前缀或对设定的解释。
2. 字数要求在 3000 字左右。
3. 注意网文的排版呼吸感，多换行，人物对话必须独立成段。
"""
        user_prompt = user_prompt_header + previous_context + user_prompt_mid + rag_context + user_prompt_end + chapter_outline + user_prompt_footer

        # --- 3. 流式请求大模型并落盘 ---
        log_func("\n>> 正在连接大模型，准备流式写入正文...\n")
        output_filepath = os.path.join(content_dir, f"{chapter_name}.txt")
        
        api_key = os.getenv("DEEPSEEK_API_KEY")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.5,
            "top_p": 0.9,
            "stream": True # 强制开启流式输出
        }

        try:
            with requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, stream=True, timeout=60) as response:
                response.raise_for_status()
                
                with open(output_filepath, 'w', encoding='utf-8') as f:
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith('data: ') and decoded_line != 'data: [DONE]':
                                try:
                                    json_data = json.loads(decoded_line[6:])
                                    if 'choices' in json_data and len(json_data['choices']) > 0:
                                        delta_content = json_data['choices'][0]['delta'].get('content', '')
                                        if delta_content:
                                            log_func(delta_content, append=True)
                                            f.write(delta_content)
                                            f.flush()
                                except json.JSONDecodeError:
                                    continue
            
            log_func(f"\n\n✅ 章节正文生成完毕！物理文件已落盘至: {output_filepath}")
            return True
        except Exception as e:
            log_func(f"\n❌ 流式生成中断或失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(project_name, chapter_name, branch="同人创作", model="deepseek-chat"):
    if not project_name or not chapter_name:
        print("error: 缺少项目名或章节名参数")
        sys.exit(1)
        
    print(f"开始静默执行小说流式生成: 项目 [{project_name}] - 章节 [{chapter_name}] - 模式 [{branch}]")
    success = NovelGenerationApp.execute_generation(project_name, chapter_name, model, branch, lambda msg, append=False: print(msg, end="" if append else "\n", flush=True))
    if not success: sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--chapter", type=str, default="")
    parser.add_argument("--branch", type=str, default="同人创作")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    args = parser.parse_args()
    
    if not args.project and len(sys.argv) == 1:
        root = tk.Tk()
        app = NovelGenerationApp(root)
        root.mainloop()
    else:
        run_headless(args.project, args.chapter, args.branch, args.model)