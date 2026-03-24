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
# 2. 导入 core 模块 (注意加 core. 前缀)
# =====================================================================
from core._core_config import BASE_DIR, PROJECT_ROOT, PROJ_DIR
from core._core_utils import smart_read_text
from core._core_llm import call_deepseek_api
from core._core_rag import RAGRetriever

class ChapterOutlineApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f5a: 章节详细大纲生成 (附加检索原文版)")
        self.root.geometry("700x500")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        frame_base = ttk.LabelFrame(self.root, text="1. 基础定位 (系统将自动识别原创/同人模式)")
        frame_base.pack(fill="x", **padding)
        
        ttk.Label(frame_base, text="目标项目名:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.project_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.project_var, width=25).grid(row=0, column=1, sticky="w", padx=5)
        
        ttk.Label(frame_base, text="本章章节名:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.chapter_name_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.chapter_name_var, width=25).grid(row=1, column=1, sticky="w", padx=5)

        frame_brief = ttk.LabelFrame(self.root, text="2. 本章核心剧情简述")
        frame_brief.pack(fill="x", **padding)
        self.brief_text = tk.Text(frame_brief, height=5, width=90)
        self.brief_text.pack(padx=5, pady=5)

        frame_model = ttk.LabelFrame(self.root, text="3. 执行配置")
        frame_model.pack(fill="x", **padding)
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Radiobutton(frame_model, text="DeepSeek V3 (标准)", variable=self.model_var, value="deepseek-chat").pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Radiobutton(frame_model, text="DeepSeek R1 (推理)", variable=self.model_var, value="deepseek-reasoner").pack(side=tk.LEFT, padx=10, pady=5)
        
        self.btn_process = ttk.Button(self.root, text="▶ 执行解析并生成大纲", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=10, width=90, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。将统一调用 1024 维 BAAI 模型进行背景检索。")

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
    def read_file_safe(filepath, max_len=None):
        if os.path.exists(filepath):
            try:
                return smart_read_text(filepath, max_len=max_len)
            except Exception:
                return ""
        return ""

    @staticmethod
    def load_all_characters(target_dir):
        char_dir = os.path.join(target_dir, "character_profiles")
        if not os.path.exists(char_dir):
            return "无角色卡数据。"
        
        char_texts = []
        for filename in os.listdir(char_dir):
            if filename.endswith(".md"):
                char_texts.append(ChapterOutlineApp.read_file_safe(os.path.join(char_dir, filename)))
        return "\n\n".join(char_texts) if char_texts else "无角色卡数据。"

    @staticmethod
    def chunk_text(text, max_len=600):
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

        world_settings = ChapterOutlineApp.read_file_safe(os.path.join(target_dir, "world_settings.md")) or "无世界观设定。"
        characters_info = ChapterOutlineApp.load_all_characters(target_dir)

        rag_context = "无历史剧情记录。"
        rag_original_text_for_append = "" 
        
        rag_db_dir = os.path.join(target_dir, "hierarchical_rag_db")
        is_fanfic_mode = os.path.exists(rag_db_dir)

        try:
            # 统一使用 _core_rag 里的 1024 维模型，彻底告别维度冲突
            retriever = RAGRetriever()
            embedder = retriever.get_embedder()
            query_vec = embedder.encode([chapter_brief]) 
            
            if is_fanfic_mode:
                log_func("自动识别为【同人模式】。正在向原著 RAG 数据库发起检索...")
                faiss_index_path = os.path.join(rag_db_dir, "plot_summary.index")
                mapping_path = os.path.join(rag_db_dir, "summary_to_raw_mapping.json")
                
                if os.path.exists(faiss_index_path) and os.path.exists(mapping_path):
                    import shutil
                    temp_read_path = "temp_read_plot_index.bin"
                    shutil.copy2(faiss_index_path, temp_read_path)
                    index = faiss.read_index(temp_read_path)
                    try: os.remove(temp_read_path)
                    except: pass
                    
                    try:
                        mapping_data = json.loads(smart_read_text(mapping_path))
                    except Exception as e:
                        log_func(f"⚠️ 无法解析 mapping 文件: {e}")
                        mapping_data = []
                    
                    distances, indices = index.search(np.array(query_vec).astype('float32'), k=3) 
                    retrieved_summaries = []
                    retrieved_raws = []
                    
                    for idx in indices[0]:
                        if idx != -1 and idx < len(mapping_data):
                            item = mapping_data[idx]
                            if isinstance(item, dict):
                                summary = item.get("summary", "")
                                raw = item.get("raw_text", "") or item.get("raw", "") or item.get("chunk", "") or item.get("raw_chunk", "") or item.get("content", "")
                                if summary: retrieved_summaries.append(summary)
                                if raw: retrieved_raws.append(raw)
                            elif isinstance(item, str):
                                retrieved_summaries.append(item)

                    if retrieved_summaries:
                        rag_context = "\n\n".join(retrieved_summaries)
                        rag_original_text_for_append = "\n\n...\n\n".join(retrieved_raws) if retrieved_raws else rag_context
                        log_func("成功召回原著中的关联设定与剧情碎片。")
                else:
                    log_func("⚠️ RAG 组件缺失，降级生成。")

            else:
                log_func("自动识别为【原创模式】。正在读取已生成的前文记录进行匹配...")
                content_dir = os.path.join(target_dir, "content")
                if os.path.exists(content_dir):
                    past_texts = []
                    for f_name in sorted(os.listdir(content_dir), key=lambda x: os.path.getmtime(os.path.join(content_dir, x))):
                        if f_name.endswith(".txt") and f_name != f"{chapter_name}.txt":
                            past_texts.append(ChapterOutlineApp.read_file_safe(os.path.join(content_dir, f_name)))
                    
                    full_past_text = "\n".join(past_texts)
                    if full_past_text.strip():
                        chunks = ChapterOutlineApp.chunk_text(full_past_text, max_len=800)
                        if chunks:
                            chunk_embeddings = embedder.encode(chunks, show_progress_bar=False)
                            index = faiss.IndexFlatL2(chunk_embeddings.shape[1])
                            index.add(np.array(chunk_embeddings).astype('float32'))
                            
                            distances, indices = index.search(np.array(query_vec).astype('float32'), k=3)
                            retrieved_chunks = [chunks[idx] for idx in indices[0] if idx != -1 and idx < len(chunks)]
                            rag_context = "\n\n...\n\n".join(retrieved_chunks)
                            rag_original_text_for_append = rag_context
                            log_func("成功召回相关前置章节片段。")
                    else:
                        log_func("尚未生成前置章节，无历史记录。")
        except Exception as e:
            log_func(f"⚠️ RAG 检索异常: {e}")

        log_func("正在请求大模型生成章节详细大纲...")
        prompt_header = """【系统指令】：
你是一个专业的小说大纲架构师。请基于提供的【前置剧情】与【世界观/角色设定】，将用户输入的【本章核心简述】扩写并生成一份结构严谨、细节丰满的【本章详细大纲】。

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
        prompt = prompt_header + world_settings + "\n\n【参考：全量角色信息卡】：\n" + characters_info + "\n\n【参考：相关历史前置剧情 (经RAG召回)】：\n" + rag_context + "\n\n【用户输入：本章核心简述】：\n" + chapter_brief + "\n"
        sys_prompt = "你是一个严谨的网文大纲架构师。只允许输出纯 Markdown 格式。"

        try:
            # 统一调用 core
            result_text = call_deepseek_api(system_prompt=sys_prompt, user_prompt=prompt, model=model, temperature=0.5)
            
            if rag_original_text_for_append and rag_original_text_for_append != "无历史剧情记录。":
                result_text += "\n\n### 三、 检索原文参考（供 f5b 模仿文风与衔接）\n"
                result_text += rag_original_text_for_append
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(result_text)
            log_func(f"✅ 大纲及关联原文生成落盘至: {save_path}")
            return True
        except Exception as e:
            log_func(f"❌ API 调用失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(project_name, chapter_name, chapter_brief_json, model="deepseek-chat"):
    import sys
    try:
        data = json.loads(chapter_brief_json)
        chapter_brief = data.get("brief", "")
    except Exception:
        chapter_brief = chapter_brief_json

    if not project_name or not chapter_name or not chapter_brief:
        print("error: 缺少项目名、章节名或剧情简述参数")
        sys.exit(1)
        
    print(f"开始静默生成章节大纲: {project_name} - {chapter_name}")
    success = ChapterOutlineApp.execute_generation(project_name, chapter_name, chapter_brief, model, print)
    if not success: sys.exit(1)

if __name__ == "__main__":
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--chapter", type=str, help="章节名", default="")
    parser.add_argument("--brief", type=str, help="本章剧情简述 (JSON或纯文本)", default="")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    args = parser.parse_args()
    
    if not args.project and len(sys.argv) == 1:
        import tkinter as tk
        from tkinter import ttk, messagebox
        root = tk.Tk()
        app = ChapterOutlineApp(root)
        root.mainloop()
    else:
        run_headless(args.project, args.chapter, args.brief, args.model)