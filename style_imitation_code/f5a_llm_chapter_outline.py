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

class ChapterOutlineApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f5a: 章节详细大纲生成 (RAG 增强版)")
        self.root.geometry("700x550")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        # 1. 项目与章节基础信息
        frame_base = ttk.LabelFrame(self.root, text="1. 基础定位")
        frame_base.pack(fill="x", **padding)
        
        ttk.Label(frame_base, text="目标项目名:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.project_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.project_var, width=25).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(frame_base, text="(如: 小说A_style_imitation)", foreground="gray").grid(row=0, column=2, sticky="w")
        
        ttk.Label(frame_base, text="本章章节名:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.chapter_name_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.chapter_name_var, width=25).grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(frame_base, text="(如: 第五十章)").grid(row=1, column=2, sticky="w")

        # 2. 用户本章构思输入
        frame_brief = ttk.LabelFrame(self.root, text="2. 本章核心剧情简述 (输入你想写的剧情，系统将自动检索前文补全细节)")
        frame_brief.pack(fill="x", **padding)
        self.brief_text = tk.Text(frame_brief, height=5, width=90)
        self.brief_text.pack(padx=5, pady=5)

        # 3. 模型与执行
        frame_model = ttk.LabelFrame(self.root, text="3. 执行配置")
        frame_model.pack(fill="x", **padding)
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Radiobutton(frame_model, text="DeepSeek V3 (标准)", variable=self.model_var, value="deepseek-chat").pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Radiobutton(frame_model, text="DeepSeek R1 (推理)", variable=self.model_var, value="deepseek-reasoner").pack(side=tk.LEFT, padx=10, pady=5)
        
        self.btn_process = ttk.Button(self.root, text="▶ 检索前置剧情并生成本章大纲", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=8, width=90, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。请确保已执行 f4 构建了本地 FAISS 检索库。")

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def start_process_thread(self):
        project_name = self.project_var.get().strip()
        chapter_name = self.chapter_name_var.get().strip()
        chapter_brief = self.brief_text.get("1.0", tk.END).strip()
        
        if not project_name or not chapter_name or not chapter_brief:
            messagebox.showwarning("提示", "项目名、章节名、剧情简述为必填项！")
            return
            
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, args=(project_name, chapter_name, chapter_brief), daemon=True).start()

    def process_logic(self, project_name, chapter_name, chapter_brief):
        model = self.model_var.get()
        result = self.execute_generation(project_name, chapter_name, chapter_brief, model, self.log)
        if result:
            messagebox.showinfo("完成", f"【{chapter_name}】详细大纲生成完毕！")
        self.btn_process.config(state="normal")

    @staticmethod
    def execute_generation(project_name, chapter_name, chapter_brief, model, log_func):
        target_dir = os.path.join(PROJ_DIR, project_name)
        if not os.path.exists(target_dir):
            log_func(f"❌ 错误: 未找到项目目录 {target_dir}")
            return False
            
        outlines_dir = os.path.join(target_dir, "chapter_structures")
        os.makedirs(outlines_dir, exist_ok=True)
        save_path = os.path.join(outlines_dir, f"{chapter_name}_outline.md")

        # 1. 尝试加载世界观设定作为底层约束
        world_settings = "无"
        ws_path = os.path.join(target_dir, "world_settings.md")
        if os.path.exists(ws_path):
            try:
                try:
                    with open(ws_path, 'r', encoding='utf-8') as f:
                        world_settings = f.read()
                except UnicodeDecodeError:
                    with open(ws_path, 'r', encoding='gbk') as f:
                        world_settings = f.read()
            except Exception as e:
                log_func(f"⚠️ 读取世界观失败: {e}")

        # 2. 尝试通过 f4 的 FAISS 检索历史剧情
        rag_context = "无历史剧情记录。"
        rag_db_dir = os.path.join(target_dir, "hierarchical_rag_db")
        faiss_index_path = os.path.join(rag_db_dir, "plot_summary.index")
        mapping_path = os.path.join(rag_db_dir, "summary_to_raw_mapping.json")
        
        if os.path.exists(faiss_index_path) and os.path.exists(mapping_path):
            log_func("正在通过 RAG 检索前置历史剧情...")
            try:
                embedder = SentenceTransformer('shibing624/text2vec-base-chinese')
                index = faiss.read_index(faiss_index_path)
                try:
                    with open(mapping_path, 'r', encoding='utf-8') as f:
                        mapping_data = json.load(f)
                except UnicodeDecodeError:
                    with open(mapping_path, 'r', encoding='gbk') as f:
                        mapping_data = json.load(f)
                
                # 用用户的简述作为 Query 搜索
                query_vec = embedder.encode([chapter_brief])
                distances, indices = index.search(np.array(query_vec).astype('float32'), k=3) # 召回最相关的3个前置节点
                
                retrieved_summaries = []
                for idx in indices[0]:
                    if idx != -1 and idx < len(mapping_data):
                        retrieved_summaries.append(mapping_data[idx]["summary"])
                
                if retrieved_summaries:
                    rag_context = "\n\n".join(retrieved_summaries)
                    log_func(f"成功召回 {len(retrieved_summaries)} 条相关历史事件作为推演依据。")
            except Exception as e:
                log_func(f"⚠️ RAG 检索失败，降级为仅依赖用户输入: {e}")
        else:
            log_func("⚠️ 未检测到 f4 历史数据库，跳过前置剧情检索。")

        # 3. 构建大模型 Prompt (严格对齐您的结构要求)
        log_func("正在请求大模型生成章节详细大纲...")
        prompt_header = f"""【系统指令】：
你是一个专业的小说大纲架构师。请基于提供的【前置剧情】与【世界观设定】，将用户输入的【本章核心简述】扩写并生成一份结构严谨、细节丰满的【本章详细大纲】。

必须严格按照以下 Markdown 格式输出，不可改变模块标题：

### 一、 本章结构
- **写作目的**：（在 推进主线情节 / 塑造人物性格 / 交代背景设定 / 渲染环境氛围 / 埋设伏笔铺垫 / 揭示升华主题 中选择或补充）
- **行文结构**：（在 总分总 / 承上启下 / 悬念设置 / 伏笔照应 / 明暗双线交织 中选择或补充）
- **叙述方式**：（在 顺叙 / 倒叙 / 插叙 / 补叙 / 平叙 中选择或补充）

### 二、 故事内容
- **核心冲突**：[总结本章的核心矛盾]
- **出场人物**：[列出本章出场人物]
- **场景情节**：
  - 场景一：[人物] [起因] [经过] [结果]
  - 场景二：[人物] [起因] [经过] [结果]
  （根据剧情复杂度适度增加场景）
- **动作细节**：
  - [某角色]：[写出一至两个极具画面感或体现性格的具体动作细节]
- **铺垫伏笔**：[写出本章埋下的身世、隐藏线索或重要设定，若无请写“无”]
- **结尾钩子**：[设计一个吸引读者阅读下一章的悬念或转折结尾]
- **其他注意**：[环境描写建议或情绪基调等]
- **禁止事项**：[列出本章绝对不能出现的雷点，如战力崩坏、人物降智等]

---
【参考：世界观与底层设定】：
"""
        prompt = prompt_header + world_settings + "\n\n【参考：相关历史前置剧情 (经RAG召回)】：\n" + rag_context + "\n\n【用户输入：本章核心简述】：\n" + chapter_brief + "\n"

        api_key = os.getenv("DEEPSEEK_API_KEY")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个严谨的网文大纲架构师。只允许输出纯 Markdown 格式。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5 # 给予一定的想象力与推演空间
        }
        
        try:
            response = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            result_text = response.json()['choices'][0]['message']['content'].strip()
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(result_text)
            log_func(f"✅ 大纲生成完成！文件已落盘至: {save_path}")
            return True
        except Exception as e:
            log_func(f"❌ API 调用失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(project_name, chapter_name, chapter_brief_json, model="deepseek-chat"):
    try:
        data = json.loads(chapter_brief_json)
        chapter_brief = data.get("brief", "")
    except Exception:
        chapter_brief = chapter_brief_json # 容错直接传字符串

    if not project_name or not chapter_name or not chapter_brief:
        print("error: 缺少项目名、章节名或剧情简述参数")
        sys.exit(1)
        
    print(f"开始静默生成章节大纲: {project_name} - {chapter_name}")
    success = ChapterOutlineApp.execute_generation(project_name, chapter_name, chapter_brief, model, print)
    if not success: sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--chapter", type=str, help="章节名，如：第五十章", default="")
    parser.add_argument("--brief", type=str, help="本章剧情简述 (JSON字符串或纯文本)", default="")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    args = parser.parse_args()
    
    if not args.project and len(sys.argv) == 1:
        root = tk.Tk()
        app = ChapterOutlineApp(root)
        root.mainloop()
    else:
        run_headless(args.project, args.chapter, args.brief, args.model)