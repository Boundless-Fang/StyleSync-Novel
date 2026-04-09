import os
import re
import shutil

from core._core_gui_runner import safe_run_app, inject_env, ThreadSafeBaseGUI
inject_env()

from core._core_config import BASE_DIR, PROJECT_ROOT, REFERENCE_DIR, STYLE_DIR, PROJ_DIR
from core._core_utils import smart_read_text, atomic_write
from core._core_llm import call_deepseek_api
from core._core_rag import RAGRetriever

class ExclusiveVocabApp(ThreadSafeBaseGUI):
    def __init__(self, root):
        super().__init__(root, title="f3a: 专属词库提取 (RAG 向量检索版)", geometry="650x450")

    def setup_custom_widgets(self):
        import tkinter as tk
        from tkinter import ttk, filedialog
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
        
        self.btn_process = ttk.Button(self.root, text="全文向量化与提取专属词库", command=lambda: self.start_process_thread(self.btn_process))
        self.btn_process.pack(pady=10)
        self.log("系统就绪。将调用 _core_rag 进行 1024 维高精度检索。")

    def select_original(self):
        import tkinter as tk
        from tkinter import filedialog
        init_dir = REFERENCE_DIR if os.path.exists(REFERENCE_DIR) else BASE_DIR
        path = filedialog.askopenfilename(initialdir=init_dir, title="选择原文", filetypes=[("Text Files", "*.txt")])
        if path: self.original_var.set(path)

    def execute_logic(self):
        import tkinter.messagebox as messagebox
        original_path = self.original_var.get()
        model = self.model_var.get()
        if not original_path:
            self.log("[ERROR] 请先选择原文文件！")
            return
            
        result = self.execute_extraction(original_path, model, self.log, project_name=None)
        if result:
            messagebox.showinfo("完成", "专属词库提取完毕，文件已落盘。")

    @staticmethod
    def execute_extraction(original_path, model, log_func, project_name=None):
        try:
            novel_name = os.path.splitext(os.path.basename(original_path))[0]
            words_path = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "statistics", "高频词.txt")

            style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
            rag_db_dir = os.path.join(style_dir, "global_rag_db")
            index_path = os.path.join(rag_db_dir, "vector.index")
            chunks_path = os.path.join(rag_db_dir, "chunks.json")

            if not os.path.exists(index_path) or not os.path.exists(chunks_path):
                 log_func("[ERROR] 致命错误：未找到全局 RAG 索引。请先执行 f0 初始化！")
                 return False

            try:
                words_text = ""
                query_keywords = []
                if os.path.exists(words_path):
                    words_text = smart_read_text(words_path)
                    matches = re.findall(r'(\S+)\(\d+\)', words_text)
                    query_keywords = matches[:100]
                else:
                    log_func("警告：未找到本地高频词文件，无法进行精准 RAG 检索。")
                    return False
            except Exception as e:
                log_func(f"读取文件失败: {e}")
                return False

            os.makedirs(style_dir, exist_ok=True)
            save_path = os.path.join(style_dir, "exclusive_vocab.md")
            
            project_save_path = None
            if project_name:
                project_dir = os.path.join(PROJ_DIR, project_name)
                os.makedirs(project_dir, exist_ok=True)
                project_save_path = os.path.join(project_dir, "exclusive_vocab.md")

            # 统一调用 _core_rag 进行安全加载与检索
            log_func("正在加载全局 RAG 索引...")
            try:
                retriever = RAGRetriever()
                index, chunks = retriever.load_index(index_path, chunks_path)
                log_func(f"已加载索引，包含 {len(chunks)} 个文本块。")
                
                log_func("正在检索与高频词关联的上下文文本块...")
                retrieved_chunks = retriever.search(index, chunks, query_keywords, k=5, batch_size=10)
                context_text = "\n...\n".join(retrieved_chunks[:30])
                log_func(f"成功召回 {min(len(retrieved_chunks), 30)} 个高相关度片段，即将请求大模型。")
                
            except Exception as e:
                log_func(f"[ERROR] 向量化或检索失败: {str(e)}")
                return False

            # 统一调用 _core_llm 请求大语言模型
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
            sys_prompt = "你是一个严谨的信息提取助手。只允许输出 Markdown 格式的纯文本列表。"

            try:
                result_text = call_deepseek_api(system_prompt=sys_prompt, user_prompt=prompt, model=model, temperature=0.2)
                
                try:
                    atomic_write(save_path, result_text, data_type='text')
                    msg = f"[INFO] 提取完成！文件已原子级落盘至: {save_path}"
                    if project_save_path:
                        shutil.copy2(save_path, project_save_path)
                        msg += f"\n已同步备份至项目目录: {project_save_path}"
                    log_func(msg)
                    return True
                except Exception as e:
                    log_func(f"[ERROR] 文件写入失败: {e}")
                    raise
            except Exception as e:
                log_func(f"[ERROR] API 调用失败: {str(e)}")
                return False
        except Exception as e:
            log_func(f"[ERROR] 分析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(target_file, project_name=None, model="deepseek-chat"):
    import sys
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
    safe_run_app(
        app_class=ExclusiveVocabApp,
        headless_func=run_headless,
        target_file="",
        project_name="",
        model=""
    )
