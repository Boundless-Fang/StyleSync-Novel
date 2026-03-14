import sys
import argparse
import jieba
import os
import math
from collections import Counter
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading

# --- 物理目录严格对齐架构图 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
INPUT_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")

PUNCTUATIONS = set("，。！？；：“”‘’（）【】《》、\n\r \t.!?,-[]")

class WordFreqAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f2a: 本地高频词提取工具")
        self.root.geometry("520x450")
        self.root.resizable(False, False)
        self.ensure_directories()
        self.create_widgets()

    def ensure_directories(self):
        for directory in [INPUT_DIR, STYLE_DIR, PROJ_DIR]:
            os.makedirs(directory, exist_ok=True)

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        frame_file = ttk.LabelFrame(self.root, text="1. 选择小说源文件 (reference_novels)")
        frame_file.pack(fill="x", **padding)

        self.file_path_var = tk.StringVar()
        ttk.Entry(frame_file, textvariable=self.file_path_var, state="readonly", width=45).grid(row=0, column=0, padx=5, pady=10)
        ttk.Button(frame_file, text="浏览...", command=self.select_file).grid(row=0, column=1, padx=5, pady=10)

        frame_settings = ttk.LabelFrame(self.root, text="2. 高频词提取策略")
        frame_settings.pack(fill="x", **padding)

        self.top_n_mode = tk.IntVar(value=1)
        ttk.Radiobutton(frame_settings, text="智能动态推荐 (基于立方根与对数TTR算法)", variable=self.top_n_mode, value=1, command=self.toggle_entry).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Label(frame_settings, text=" * 适配长文本，防止提取量爆炸", foreground="gray").grid(row=1, column=0, columnspan=2, sticky="w", padx=25)

        ttk.Radiobutton(frame_settings, text="手动指定提取前 N 个:", variable=self.top_n_mode, value=2, command=self.toggle_entry).grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.manual_var = tk.StringVar(value="500")
        self.entry_manual = ttk.Entry(frame_settings, textvariable=self.manual_var, state="disabled", width=10)
        self.entry_manual.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        self.btn_run = ttk.Button(self.root, text="▶ 开始提取高频词", command=self.start_processing)
        self.btn_run.pack(pady=10)

        self.log_text = tk.Text(self.root, height=8, width=65, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。")

    def toggle_entry(self):
        self.entry_manual.config(state="normal" if self.top_n_mode.get() == 2 else "disabled")

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def select_file(self):
        init_dir = INPUT_DIR if os.path.exists(INPUT_DIR) else BASE_DIR
        path = filedialog.askopenfilename(initialdir=init_dir, title="选择原文", filetypes=[("Text Files", "*.txt")])
        if path: self.file_path_var.set(path)

    def start_processing(self):
        if not self.file_path_var.get():
            messagebox.showwarning("警告", "请先选择小说源文件！")
            return
        if self.top_n_mode.get() == 2 and not self.manual_var.get().isdigit():
            messagebox.showwarning("警告", "请输入正确的数字！")
            return
            
        self.btn_run.config(state="disabled")
        threading.Thread(target=self.run_extraction, args=(self.file_path_var.get(),), daemon=True).start()

    def run_extraction(self, file_path):
        try:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='gbk') as f:
                    content = f.read()

            novel_name = os.path.splitext(os.path.basename(file_path))[0]
            
            # 严格对齐架构图路径
            out_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "statistics")
            os.makedirs(out_dir, exist_ok=True)

            self.log(f"开始提取《{novel_name}》的高频词...")
            report = []
            
            words = jieba.lcut(content)
            valid_words = [w for w in words if w.strip() and w not in PUNCTUATIONS]
            
            if len(valid_words) <= 1:
                self.log("文本过少，无法提取。")
                return

            # 计算提取数量
            if self.top_n_mode.get() == 1:
                unique = len(set(valid_words))
                log_ttr = math.log10(unique) / math.log10(len(valid_words)) if len(valid_words) > 1 else 0
                calc_n = int(50 * log_ttr * (len(valid_words) ** (1/3.0))) if len(valid_words) > 1 else 100
                top_n = max(100, min(8000, calc_n))
                self.log(f"动态算法建议提取量: Top {top_n}")
            else:
                top_n = int(self.manual_var.get())
                self.log(f"手动提取量: Top {top_n}")

            counts = Counter(valid_words).most_common(top_n)
            report.append(f"【高频词列表 (提取前 {top_n} 个)】\n" + "-"*40)
            
            for i in range(0, len(counts), 5):
                chunk = counts[i:i + 5]
                report.append("  ".join([f"{w}({c})" for w, c in chunk]))

            save_path = os.path.join(out_dir, "高频词.txt")
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(report))

            self.log(f"✅ 提取完成！已保存至: {save_path}")
        except Exception as e:
            self.log(f"错误: {str(e)}")
        finally:
            self.btn_run.config(state="normal")

# =========================================================================================
# 后台静默执行逻辑 
# =========================================================================================
def run_headless(file_path):
    if not os.path.exists(file_path):
        sys.exit(1)
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(file_path, 'r', encoding='gbk') as f:
            content = f.read()

    novel_name = os.path.splitext(os.path.basename(file_path))[0]
    
    # 严格对齐架构图路径
    out_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "statistics")
    os.makedirs(out_dir, exist_ok=True)

    words = jieba.lcut(content)
    valid_words = [w for w in words if w.strip() and w not in PUNCTUATIONS]
    if len(valid_words) <= 1: 
        sys.exit(0)

    # 强制动态算法
    unique = len(set(valid_words))
    log_ttr = math.log10(unique) / math.log10(len(valid_words)) if len(valid_words) > 1 else 0
    top_n = max(100, min(8000, int(50 * log_ttr * (len(valid_words) ** (1/3.0)))))

    counts = Counter(valid_words).most_common(top_n)
    report = [f"【高频词列表 (提取前 {top_n} 个)】\n" + "-"*40]
    
    for i in range(0, len(counts), 5):
        chunk = counts[i:i + 5]
        report.append("  ".join([f"{w}({c})" for w, c in chunk]))

    with open(os.path.join(out_dir, "高频词.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(report))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, default="")
    parser.add_argument("--project", type=str, default="") # 占位，静默模式中主动忽略
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        root = tk.Tk()
        app = WordFreqAnalyzerApp(root)
        root.mainloop()
    else:
        if not args.target_file and unknown and not unknown[0].startswith('--'):
            args.target_file = unknown[0]
        # 忽略 project，确保完全落盘在 reference 的归属文件树中
        run_headless(args.target_file)