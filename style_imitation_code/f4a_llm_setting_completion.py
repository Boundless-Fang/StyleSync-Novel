import sys
import argparse
import os
import json
import requests
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from dotenv import load_dotenv

# 【关键配置】：强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
load_dotenv()

# --- 物理目录对齐 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")

class SettingCompletionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f4a: 设定补全 (世界观/角色卡)")
        self.root.geometry("750x650")
        self.root.resizable(False, False)
        
        # 变量存储
        self.original_var = tk.StringVar()
        self.model_var = tk.StringVar(value="deepseek-chat")
        
        self.create_widgets()

    def create_widgets(self):
        # 顶部基础配置
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(top_frame, text="参考原文(.txt):").grid(row=0, column=0, sticky="w")
        ttk.Entry(top_frame, textvariable=self.original_var, state="readonly", width=55).grid(row=0, column=1, padx=5)
        ttk.Button(top_frame, text="浏览...", command=self.select_original).grid(row=0, column=2, padx=5)
        
        ttk.Label(top_frame, text="处理模型:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Radiobutton(top_frame, text="DeepSeek V3", variable=self.model_var, value="deepseek-chat").grid(row=1, column=1, sticky="w")

        # 选项卡
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.build_worldview_tab()
        self.build_character_tab()

        # 日志输出
        self.log_text = tk.Text(self.root, height=6, state="disabled", bg="#f8f9fa")
        self.log_text.pack(fill="x", padx=10, pady=5)
        self.log("系统就绪。请选择补全模式并填写必要信息。")

    def build_worldview_tab(self):
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
            
        ttk.Button(frame, text="▶ 执行世界观补全", command=lambda: self.start_process("worldview")).grid(row=len(fields), column=1, sticky="e", pady=10)

    def build_character_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="角色卡补全")
        
        self.char_vars = {}
        # 基础属性
        ttk.Label(frame, text="目标角色名:").grid(row=0, column=0, sticky="w", padx=10, pady=2)
        self.char_vars["name"] = tk.StringVar()
        ttk.Entry(frame, textvariable=self.char_vars["name"], width=20).grid(row=0, column=1, sticky="w", pady=2)
        
        ttk.Label(frame, text="人物类型 (必填):").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.char_vars["char_type"] = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.char_vars["char_type"], values=["男主角", "女主角", "配角", "反派"], width=17).grid(row=1, column=1, sticky="w", pady=2)
        
        ttk.Label(frame, text="人物塑造 (必填):").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.char_vars["char_shape"] = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.char_vars["char_shape"], values=["圆形人物", "扁平人物"], width=17).grid(row=2, column=1, sticky="w", pady=2)

        # 相关信息 (至少2项)
        ttk.Label(frame, text="--- 二、相关信息 (至少填2项) ---", foreground="blue").grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        sec2_fields = [("身份", "identity"), ("性格", "personality"), ("外貌等", "appearance"), ("能力特点/境界", "ability"), ("年龄与经历", "experience")]
        for i, (label, key) in enumerate(sec2_fields):
            ttk.Label(frame, text=label).grid(row=4+i, column=0, sticky="w", padx=20, pady=2)
            self.char_vars[key] = tk.StringVar()
            ttk.Entry(frame, textvariable=self.char_vars[key], width=50).grid(row=4+i, column=1, sticky="w", pady=2)
            
        # 态度 (至少1项)
        ttk.Label(frame, text="--- 四、对主要角色态度 (至少填1项) ---", foreground="blue").grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        ttk.Label(frame, text="态度输入:").grid(row=10, column=0, sticky="w", padx=20, pady=2)
        self.char_vars["attitude"] = tk.StringVar()
        ttk.Entry(frame, textvariable=self.char_vars["attitude"], width=50).grid(row=10, column=1, sticky="w", pady=2)

        ttk.Button(frame, text="▶ 执行角色卡补全", command=lambda: self.start_process("character")).grid(row=11, column=1, sticky="e", pady=10)

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

    def start_process(self, mode):
        # 1. 验证逻辑
        data_to_pass = {}
        if mode == "worldview":
            if not self.wv_vars["worldview"].get().strip():
                messagebox.showerror("验证失败", "【世界观】为必填项！")
                return
            if not self.wv_vars["power_system"].get().strip():
                messagebox.showerror("验证失败", "【力量体系】不能为空！")
                return
            data_to_pass = {k: v.get().strip() for k, v in self.wv_vars.items()}
            
        elif mode == "character":
            if not self.char_vars["name"].get().strip() or not self.char_vars["char_type"].get().strip() or not self.char_vars["char_shape"].get().strip():
                messagebox.showerror("验证失败", "名字、人物类型、人物塑造 为必填项！")
                return
                
            sec2_filled = sum(1 for k in ["identity", "personality", "appearance", "ability", "experience"] if self.char_vars[k].get().strip())
            if sec2_filled < 2:
                messagebox.showerror("验证失败", "【二、相关信息】至少需要填写 2 项！")
                return
                
            if not self.char_vars["attitude"].get().strip():
                messagebox.showerror("验证失败", "【四、对主要角色的态度】至少需要填写 1 项！")
                return
            data_to_pass = {k: v.get().strip() for k, v in self.char_vars.items()}

        threading.Thread(target=self.execute_completion, args=(self.original_var.get(), mode, data_to_pass, self.model_var.get(), self.log), daemon=True).start()

    @staticmethod
    def execute_completion(original_path, mode, json_data, model, log_func, project_name=None):
        log_func(f"正在进行【{mode}】模式设定补全...")
        
        # 确定目标目录
        target_dir = PROJ_DIR
        if project_name:
            target_dir = os.path.join(PROJ_DIR, project_name)
            os.makedirs(target_dir, exist_ok=True)

        original_text = ""
        if original_path and os.path.exists(original_path):
            try:
                try:
                    with open(original_path, 'r', encoding='utf-8') as f:
                        original_text = f.read(20000) # 提供两万字上下文参考
                except UnicodeDecodeError:
                    with open(original_path, 'r', encoding='gbk') as f:
                        original_text = f.read(20000)
            except Exception as e:
                log_func(f"读取文件失败: {e}")
                return False

        # 构建 Prompt
        if mode == "worldview":
            save_path = os.path.join(target_dir, "world_settings.md")
            prompt_header = """【系统指令】：
用户提供了小说的部分世界观设定。请你阅读参考文本，结合用户已给出的设定，将其余空缺部分补全。
如果有无法从文本中得出的信息，请基于小说的基础逻辑进行合理推演，并在补全项后标注“（推演补全）”。
必须输出完整的 Markdown 结构。

【用户已提供的设定】：
"""
            prompt = prompt_header + json.dumps(json_data, ensure_ascii=False, indent=2) + "\n\n【参考原文片段】：\n" + original_text

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
            prompt = prompt_header + json.dumps(json_data, ensure_ascii=False, indent=2) + "\n\n【参考原文片段】：\n" + original_text

        api_key = os.getenv("DEEPSEEK_API_KEY")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个严谨的设定补全专家。只允许输出 Markdown 格式的纯文本。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4
        }
        
        try:
            response = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            result_text = response.json()['choices'][0]['message']['content'].strip()
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(result_text)
            log_func(f"✅ 补全完成！文件落盘至: {save_path}")
            return True
        except Exception as e:
            log_func(f"❌ API 调用失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(target_file, mode, json_string, project_name=None, model="deepseek-chat"):
    try:
        json_data = json.loads(json_string)
    except json.JSONDecodeError:
        print("error: json_data 解析失败")
        sys.exit(1)
        
    print(f"开始静默执行设定补全 (模式: {mode})")
    success = SettingCompletionApp.execute_completion(target_file, mode, json_data, model, print, project_name)
    if not success: sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, default="")
    parser.add_argument("--mode", type=str, help="worldview 或 character", default="")
    parser.add_argument("--json_data", type=str, help="以 JSON 字符串形式传入的表单数据", default="")
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    args, unknown = parser.parse_known_args()
    
    if not args.mode and len(sys.argv) == 1:
        root = tk.Tk()
        app = SettingCompletionApp(root)
        root.mainloop()
    else:
        if not args.mode or not args.json_data:
            print("error: 静默模式下必须提供 --mode 和 --json_data 参数")
            sys.exit(1)
        run_headless(args.target_file, args.mode, args.json_data, args.project, args.model)