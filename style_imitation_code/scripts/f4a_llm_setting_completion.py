import os
import json
import shutil

from core._core_gui_runner import safe_run_app, inject_env, ThreadSafeBaseGUI
inject_env()

from core._core_config import BASE_DIR, PROJECT_ROOT, REFERENCE_DIR, STYLE_DIR, PROJ_DIR
from core._core_llm import call_deepseek_api
from core._core_utils import atomic_write
from core._core_rag import RAGRetriever

class SettingCompletionApp(ThreadSafeBaseGUI):
    def __init__(self, root):
        super().__init__(root, title="f4a: 设定补全 (世界观/角色卡)", geometry="750x650")

    def setup_custom_widgets(self):
        import tkinter as tk
        from tkinter import ttk, filedialog
        padding = {'padx': 10, 'pady': 8}

        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", padx=10, pady=5)
        
        self.original_var = tk.StringVar()
        ttk.Label(top_frame, text="参考原文(.txt):").grid(row=0, column=0, sticky="w")
        ttk.Entry(top_frame, textvariable=self.original_var, state="readonly", width=55).grid(row=0, column=1, padx=5)
        ttk.Button(top_frame, text="浏览...", command=self.select_original).grid(row=0, column=2, padx=5)
        
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Label(top_frame, text="处理模型:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Radiobutton(top_frame, text="DeepSeek V3", variable=self.model_var, value="deepseek-chat").grid(row=1, column=1, sticky="w")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.build_worldview_tab()
        self.build_character_tab()
        self.log("系统就绪。请选择补全模式并填写必要信息。")

    def build_worldview_tab(self):
        import tkinter as tk
        from tkinter import ttk
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="世界观补全")
        
        self.wv_vars = {}
        fields = [
            ("世界观 (必填)", "worldview"), ("力量体系 (必填)", "power_system"),
            ("类型", "type"), ("女主数量", "heroines"),
            ("核心爽点/金手指", "cheat"), ("出场角色及别名", "characters"),
            ("种族/阵营", "factions"), ("历史/传说", "history"),
            ("资源", "resources"), ("其他", "others")
        ]
        
        for i, (label_text, key) in enumerate(fields):
            ttk.Label(frame, text=label_text).grid(row=i, column=0, sticky="w", padx=10, pady=4)
            var = tk.StringVar()
            self.wv_vars[key] = var
            ttk.Entry(frame, textvariable=var, width=60).grid(row=i, column=1, padx=5, pady=4)
            
        ttk.Button(frame, text="执行世界观补全", command=lambda: self.start_completion_thread("worldview")).grid(row=len(fields), column=1, sticky="e", pady=10)

    def build_character_tab(self):
        import tkinter as tk
        from tkinter import ttk
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="角色卡补全")
        
        self.char_vars = {}
        ttk.Label(frame, text="目标角色名:").grid(row=0, column=0, sticky="w", padx=10, pady=2)
        self.char_vars["name"] = tk.StringVar()
        ttk.Entry(frame, textvariable=self.char_vars["name"], width=20).grid(row=0, column=1, sticky="w", pady=2)
        
        ttk.Label(frame, text="人物类型 (必填):").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.char_vars["char_type"] = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.char_vars["char_type"], values=["男主角", "女主角", "配角", "反派"], width=17).grid(row=1, column=1, sticky="w", pady=2)
        
        ttk.Label(frame, text="人物塑造 (必填):").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.char_vars["char_shape"] = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.char_vars["char_shape"], values=["圆形人物", "扁平人物"], width=17).grid(row=2, column=1, sticky="w", pady=2)

        ttk.Label(frame, text="--- 二、相关信息 (至少填2项) ---", foreground="blue").grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        sec2_fields = [("身份", "identity"), ("性格", "personality"), ("外貌等", "appearance"), ("能力特点/境界", "ability"), ("年龄与经历", "experience")]
        for i, (label, key) in enumerate(sec2_fields):
            ttk.Label(frame, text=label).grid(row=4+i, column=0, sticky="w", padx=20, pady=2)
            self.char_vars[key] = tk.StringVar()
            ttk.Entry(frame, textvariable=self.char_vars[key], width=50).grid(row=4+i, column=1, sticky="w", pady=2)
            
        ttk.Label(frame, text="--- 四、对主要角色态度 (至少填1项) ---", foreground="blue").grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        ttk.Label(frame, text="态度输入:").grid(row=10, column=0, sticky="w", padx=20, pady=2)
        self.char_vars["attitude"] = tk.StringVar()
        ttk.Entry(frame, textvariable=self.char_vars["attitude"], width=50).grid(row=10, column=1, sticky="w", pady=2)

        ttk.Button(frame, text="执行角色卡补全", command=lambda: self.start_completion_thread("character")).grid(row=11, column=1, sticky="e", pady=10)

    def select_original(self):
        import tkinter as tk
        from tkinter import filedialog
        init_dir = REFERENCE_DIR if os.path.exists(REFERENCE_DIR) else BASE_DIR
        path = filedialog.askopenfilename(initialdir=init_dir, filetypes=[("Text Files", "*.txt")])
        if path: self.original_var.set(path)

    def start_completion_thread(self, mode):
        # 这种多 tab 结构需要自定义调度逻辑，或者动态绑定 execute_logic
        self.current_mode = mode
        self.start_process_thread(None) # 临时传入 None，基类会处理 is_running

    def execute_logic(self):
        import tkinter.messagebox as messagebox
        mode = getattr(self, "current_mode", "worldview")
        data_to_pass = {}
        if mode == "worldview":
            if not self.wv_vars["worldview"].get().strip():
                self.log("[ERROR] 【世界观】为必填项！")
                return
            if not self.wv_vars["power_system"].get().strip():
                self.log("[ERROR] 【力量体系】不能为空！")
                return
            data_to_pass = {k: v.get().strip() for k, v in self.wv_vars.items()}
            
        elif mode == "character":
            if not self.char_vars["name"].get().strip() or not self.char_vars["char_type"].get().strip() or not self.char_vars["char_shape"].get().strip():
                self.log("[ERROR] 名字、人物类型、人物塑造 为必填项！")
                return
                
            sec2_filled = sum(1 for k in ["identity", "personality", "appearance", "ability", "experience"] if self.char_vars[k].get().strip())
            if sec2_filled < 2:
                self.log("[ERROR] 【二、相关信息】至少需要填写 2 项！")
                return
                
            if not self.char_vars["attitude"].get().strip():
                self.log("[ERROR] 【四、对主要角色的态度】至少需要填写 1 项！")
                return
            data_to_pass = {k: v.get().strip() for k, v in self.char_vars.items()}

        success = self.execute_completion(self.original_var.get(), mode, data_to_pass, self.model_var.get(), self.log)
        if success:
            messagebox.showinfo("完成", f"{mode} 设定补全任务已完成。")

    @staticmethod
    def execute_completion(original_path, mode, json_data, model, log_func, project_name=None):
        log_func(f"正在进行【{mode}】模式设定补全 (RAG 加速版)...")
        
        target_dir = PROJ_DIR
        if project_name:
            target_dir = os.path.join(PROJ_DIR, project_name)
            os.makedirs(target_dir, exist_ok=True)

        if not original_path:
             log_func("[ERROR] 错误：未提供参考原文路径，无法定位 RAG 索引。")
             return False
             
        novel_name = os.path.splitext(os.path.basename(original_path))[0]
        style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
        rag_db_dir = os.path.join(style_dir, "global_rag_db")
        
        index_path = os.path.join(rag_db_dir, "vector.index")
        chunks_path = os.path.join(rag_db_dir, "chunks.json")

        if not os.path.exists(index_path) or not os.path.exists(chunks_path):
             log_func("[ERROR] 致命错误：未找到全局 RAG 索引。请先执行 f0 初始化！")
             return False

        log_func("正在加载全局 RAG 索引...")
        try:
            retriever = RAGRetriever()
            index, chunks = retriever.load_index(index_path, chunks_path)
            log_func(f"已加载索引，包含 {len(chunks)} 个文本块。")
        except Exception as e:
            log_func(f"[ERROR] 索引加载失败: {str(e)}")
            return False

        queries = []
        if mode == "worldview":
            for key, value in json_data.items():
                if value and str(value).strip():
                     queries.append(str(value).strip())
            queries.extend(["世界观", "力量体系", "境界", "宗门", "历史", "传说", "地图", "势力"])
            
        elif mode == "character":
            char_name = json_data.get("name", "")
            if char_name:
                queries.append(char_name)
                queries.extend([
                    f"{char_name} 外貌", f"{char_name} 性格", f"{char_name} 身份", 
                    f"{char_name} 说话", f"{char_name} 战斗", f"{char_name} 经历"
                ])
            for key, value in json_data.items():
                if value and str(value).strip() and key != "name":
                    queries.append(str(value).strip())

        log_func(f"正在基于 {len(queries)} 个关键信息点进行 RAG 检索...")
        try:
            retrieved_chunks = retriever.search(index, chunks, queries, k=5, batch_size=5)
            context_text = "\n...\n".join(retrieved_chunks[:40]) 
            log_func(f"成功召回 {min(len(retrieved_chunks), 40)} 个高相关度片段。")
            
        except Exception as e:
            log_func(f"[ERROR] RAG 检索失败: {str(e)}")
            return False

        if mode == "worldview":
            save_path = os.path.join(target_dir, "world_settings.md")
            prompt_header = """【系统指令】：
用户提供了小说的部分世界观设定。请你阅读参考文本，结合用户已给出的设定，将其余空缺部分补全。
如果有无法从文本中得出的信息，请基于小说的基础逻辑进行合理推演，并在补全项后标注“（推演补全）”。
必须输出完整的 Markdown 结构。

【用户已提供的设定】：
"""
            prompt = prompt_header + json.dumps(json_data, ensure_ascii=False, indent=2) + "\n\n【参考原文片段 (RAG 检索)】：\n" + context_text

        elif mode == "character":
            char_name = json_data.get("name", "未知角色")
            char_dir = os.path.join(target_dir, "character_profiles")
            os.makedirs(char_dir, exist_ok=True)
            save_path = os.path.join(char_dir, f"{char_name}.md")
            prompt_header = f"""【系统指令】：
用户提供了角色【{char_name}】的部分设定。请结合原文片段，补全该角色缺失的信息（包括未填写的相关信息、价值观排序、语言习惯等）。
必须严格遵循原文，如果在文本中确实没有提及，请填“未知”。必须使用标准的 Markdown 结构输出全套角色信息卡。

【用户已提供的部分设定】：
"""
            prompt = prompt_header + json.dumps(json_data, ensure_ascii=False, indent=2) + "\n\n【参考原文片段 (RAG 检索)】：\n" + context_text

        sys_prompt = "你是一个严谨的设定补全专家。只允许输出 Markdown 格式的纯文本。"

        try:
            result_text = call_deepseek_api(system_prompt=sys_prompt, user_prompt=prompt, model=model, temperature=0.4)
            atomic_write(save_path, result_text, data_type='text')
            log_func(f"[INFO] 补全完成！文件已原子级落盘至: {save_path}")
            return True
        except Exception as e:
            log_func(f"[ERROR] API 调用失败: {str(e)}")
            return False

def run_headless(target_file, mode, json_data, project_name=None, model="deepseek-chat"):
    import sys
    if isinstance(json_data, str):
        try:
            json_data = json.loads(json_data)
        except json.JSONDecodeError:
            print("error: json_data 解析失败")
            sys.exit(1)
        
    print(f"开始静默执行设定补全 (模式: {mode})")
    success = SettingCompletionApp.execute_completion(target_file, mode, json_data, model, print, project_name)
    if not success: sys.exit(1)

if __name__ == "__main__":
    safe_run_app(
        app_class=SettingCompletionApp,
        headless_func=run_headless,
        target_file="",
        mode="",
        json_data="",
        project_name="",
        model=""
    )
