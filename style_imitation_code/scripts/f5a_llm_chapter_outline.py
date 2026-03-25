# --- File: f5a_llm_chapter_outline.py ---
import os
import json
import argparse
import threading
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
# 2. 导入 core 模块
# =====================================================================
from core._core_config import BASE_DIR, PROJECT_ROOT, PROJ_DIR
from core._core_utils import smart_read_text
from core._core_llm import call_deepseek_api
from core._core_rag import RAGRetriever

class ChapterOutlineApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f5a: 章节详细大纲生成 (动态角色过滤版)")
        self.root.geometry("750x650")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        frame_base = ttk.LabelFrame(self.root, text="1. 基础定位")
        frame_base.pack(fill="x", **padding)
        
        ttk.Label(frame_base, text="目标项目名:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.project_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.project_var, width=30).grid(row=0, column=1, sticky="w", padx=5)
        
        ttk.Label(frame_base, text="本章章节名:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.chapter_name_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.chapter_name_var, width=30).grid(row=1, column=1, sticky="w", padx=5)

        frame_brief = ttk.LabelFrame(self.root, text="2. 本章核心剧情简述 (系统将根据此内容自动筛选出场角色)")
        frame_brief.pack(fill="x", **padding)
        self.brief_text = tk.Text(frame_brief, height=8, width=90)
        self.brief_text.pack(padx=5, pady=5)
        self.brief_text.insert("1.0", "在这里输入本章打算写什么的简要构思...\n提示：提及角色名字（如：萧炎、药老）可触发角色卡自动加载。")

        frame_model = ttk.LabelFrame(self.root, text="3. 执行配置")
        frame_model.pack(fill="x", **padding)
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Radiobutton(frame_model, text="DeepSeek V3 (标准)", variable=self.model_var, value="deepseek-chat").pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Radiobutton(frame_model, text="DeepSeek R1 (推理)", variable=self.model_var, value="deepseek-reasoner").pack(side=tk.LEFT, padx=10, pady=5)
        
        self.btn_process = ttk.Button(self.root, text="▶ 智能解析背景并生成精细大纲", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=12, width=95, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。已启用【动态角色卡过滤机制】，优化 Token 使用效率。")

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def start_process_thread(self):
        import tkinter.messagebox as messagebox
        project_name = self.project_var.get().strip()
        chapter_name = self.chapter_name_var.get().strip()
        chapter_brief = self.brief_text.get("1.0", tk.END).strip()
        
        if not project_name or not chapter_name or len(chapter_brief) < 5:
            messagebox.showwarning("提示", "项目名、章节名及有效的剧情简述均为必填！")
            return
            
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, args=(project_name, chapter_name, chapter_brief), daemon=True).start()

    def process_logic(self, project_name, chapter_name, chapter_brief):
        import tkinter.messagebox as messagebox
        model = self.model_var.get()
        result = self.execute_generation(project_name, chapter_name, chapter_brief, model, self.log)
        if result:
            messagebox.showinfo("完成", f"【{chapter_name}】详细大纲生成完毕！")
        self.btn_process.config(state="normal")

    @staticmethod
    def read_file_safe(filepath, max_len=None):
        if os.path.exists(filepath):
            try:
                return smart_read_text(filepath, max_len=max_len)
            except Exception:
                return ""
        return ""

    @staticmethod
    def get_filtered_characters(target_dir, chapter_brief, log_func):
        """
        【关键优化】：动态扫描简述，按需加载角色卡
        """
        char_dir = os.path.join(target_dir, "character_profiles")
        if not os.path.exists(char_dir):
            return "无相关角色卡数据。"
        
        all_char_files = [f for f in os.listdir(char_dir) if f.endswith(".md")]
        relevant_texts = []
        found_names = []

        for f_name in all_char_files:
            char_name_base = os.path.splitext(f_name)[0]
            # 检查角色名是否出现在简述中
            if char_name_base in chapter_brief:
                content = ChapterOutlineApp.read_file_safe(os.path.join(char_dir, f_name))
                if content:
                    relevant_texts.append(content)
                    found_names.append(char_name_base)
        
        if not relevant_texts:
            log_func("⚠️ 未在简述中检测到特定角色名，将跳过角色卡深度注入（仅依赖世界观）。")
            return "本章节未提及特定已知角色卡中的人物。"
        
        log_func(f"✅ 检测到本章关键角色: {', '.join(found_names)}，已成功注入其专属角色卡。")
        return "\n\n---\n\n".join(relevant_texts)

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
    def execute_generation(project_name, chapter_name, chapter_brief, model, log_func):
        target_dir = os.path.join(PROJ_DIR, project_name)
        if not os.path.exists(target_dir):
            log_func(f"❌ 错误: 未找到项目目录 {target_dir}")
            return False
            
        outlines_dir = os.path.join(target_dir, "chapter_structures")
        os.makedirs(outlines_dir, exist_ok=True)
        save_path = os.path.join(outlines_dir, f"{chapter_name}_outline.md")

        # 1. 加载设定
        world_settings = ChapterOutlineApp.read_file_safe(os.path.join(target_dir, "world_settings.md")) or "无详细世界观。"
        
        # 2. 【执行优化】筛选角色卡
        characters_info = ChapterOutlineApp.get_filtered_characters(target_dir, chapter_brief, log_func)

        # 3. RAG 逻辑
        rag_context = "无历史剧情参考。"
        rag_original_text_for_append = "" 
        
        rag_db_dir = os.path.join(target_dir, "hierarchical_rag_db")
        is_fanfic_mode = os.path.exists(rag_db_dir)

        try:
            retriever = RAGRetriever()
            embedder = retriever.get_embedder()
            query_vec = embedder.encode([chapter_brief]) 
            
            if is_fanfic_mode:
                log_func("模式识别: 同人模式。正在检索原著关联片段...")
                faiss_index_path = os.path.join(rag_db_dir, "plot_summary.index")
                mapping_path = os.path.join(rag_db_dir, "summary_to_raw_mapping.json")
                
                if os.path.exists(faiss_index_path):
                    # 采用 core 层提供的安全加载与检索
                    import shutil
                    temp_read_path = f"temp_idx_{os.getpid()}.bin"
                    shutil.copy2(faiss_index_path, temp_read_path)
                    index = faiss.read_index(temp_read_path)
                    os.remove(temp_read_path)
                    
                    mapping_data = json.loads(smart_read_text(mapping_path))
                    distances, indices = index.search(np.array(query_vec).astype('float32'), k=3)
                    
                    retrieved_summaries, retrieved_raws = [], []
                    for idx in indices[0]:
                        if idx != -1 and idx < len(mapping_data):
                            item = mapping_data[idx]
                            retrieved_summaries.append(item.get("summary", ""))
                            retrieved_raws.append(item.get("raw_chunk", ""))

                    rag_context = "\n\n".join(retrieved_summaries)
                    rag_original_text_for_append = "\n\n...\n\n".join(retrieved_raws)
                    log_func("✅ 成功找回原著相关背景。")
            else:
                log_func("模式识别: 原创模式。正在基于前文内容进行 RAG 衔接检索...")
                # 原创模式搜索前文 content/ 文件夹中的内容
                content_dir = os.path.join(target_dir, "content")
                past_files = sorted([f for f in os.listdir(content_dir) if f.endswith(".txt") and f != f"{chapter_name}.txt"])
                if past_files:
                    full_past = "\n".join([ChapterOutlineApp.read_file_safe(os.path.join(content_dir, f)) for f in past_files])
                    chunks = ChapterOutlineApp.chunk_text(full_past, 1000)
                    if chunks:
                        chunk_embs = embedder.encode(chunks)
                        idx_tmp = faiss.IndexFlatL2(chunk_embs.shape[1])
                        idx_tmp.add(np.array(chunk_embs).astype('float32'))
                        _, indices = idx_tmp.search(np.array(query_vec).astype('float32'), k=3)
                        retrieved = [chunks[i] for i in indices[0] if i != -1]
                        rag_context = "\n\n---\n\n".join(retrieved)
                        rag_original_text_for_append = rag_context
                
        except Exception as e:
            log_func(f"⚠️ RAG 模块非致命异常: {e}")

        # 4. 请求模型
        prompt_header = """你是一个顶级网文编剧。请根据以下信息，为用户输入的“本章核心简述”扩写一份【逻辑极其严密、冲突激烈、节奏紧凑】的章节大纲。

### 核心任务清单：
1. 剧情扩写：严禁复述简述，必须将简述中的模糊点具体化。
2. 人物对齐：必须符合所提供的角色卡性格与力量等级。
3. 伏笔埋设：在大纲中预留至少一个悬念点。

请严格按以下 Markdown 格式输出：

### 一、 核心要素
- **写作目的**：
- **场景分布**：（场景一、场景二...）
- **核心冲突**：

### 二、 细化大纲
- **开篇（衔接前文）**：[具体描写]
- **发展（矛盾升级）**：[具体描写，含动作指令]
- **高潮（核心冲突）**：[具体描写，含情绪指令]
- **结尾（悬念钩子）**：[具体描写，为下一章留扣]

### 三、 细节注意
- **关键动作建议**：
- **雷点/禁忌**：

---
【背景设定】：
"""
        user_input = f"""{prompt_header}
[世界观与底层设定]
{world_settings}

[出场关键角色卡]
{characters_info}

[关联前置剧情/原著背景]
{rag_context}

[用户本章简述]
{chapter_brief}
"""
        sys_prompt = "你是一个专业的小说大纲设计师，严禁废话，只输出 Markdown。"

        try:
            log_func("正在连接 DeepSeek 执行深度创作...")
            result_text = call_deepseek_api(system_prompt=sys_prompt, user_prompt=user_input, model=model, temperature=0.6)
            
            # 附加检索原文供 f5b 学习
            if rag_original_text_for_append:
                result_text += "\n\n### 四、 检索到的原文参考（供 f5b 模仿语感）\n"
                result_text += rag_original_text_for_append
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(result_text)
            log_func(f"✅ 生成成功！大纲已保存至: {save_path}")
            return True
        except Exception as e:
            log_func(f"❌ 接口请求失败: {str(e)}")
            return False

def run_headless(project_name, chapter_name, chapter_brief_json, model="deepseek-chat"):
    import sys
    try:
        data = json.loads(chapter_brief_json)
        chapter_brief = data.get("brief", "")
    except Exception:
        chapter_brief = chapter_brief_json

    if not project_name or not chapter_name:
        print("error: 缺少必要参数")
        sys.exit(1)
        
    print(f"静默生成中: {project_name} - {chapter_name}")
    ChapterOutlineApp.execute_generation(project_name, chapter_name, chapter_brief, model, print)

if __name__ == "__main__":
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--chapter", type=str, default="")
    parser.add_argument("--brief", type=str, default="")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    args = parser.parse_args()
    
    if not args.project and len(sys.argv) == 1:
        # Tkinter 下沉加载
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        app = ChapterOutlineApp(root)
        root.mainloop()
    else:
        run_headless(args.project, args.chapter, args.brief, args.model)