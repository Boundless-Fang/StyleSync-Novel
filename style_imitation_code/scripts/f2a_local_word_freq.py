# --- File: scripts/f2a_local_word_freq.py ---
import os
import math
import argparse
import threading
from collections import Counter
import jieba

# =====================================================================
# 1. 跨目录寻址：将父目录(style_imitation_code)加入环境变量
# =====================================================================
import sys
from core._core_gui_runner import safe_run_app

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    tk = None
    ttk = None
current_dir = os.path.dirname(os.path.abspath(__file__)) # 指向 scripts/
parent_dir = os.path.dirname(current_dir)                # 指向 style_imitation_code/
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# =====================================================================
# 2. 导入 core 模块 (注意加 core. 前缀)
# =====================================================================
from core._core_config import BASE_DIR, PROJECT_ROOT, REFERENCE_DIR, STYLE_DIR, PROJ_DIR
from core._core_utils import smart_read_text, atomic_write

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
        for directory in [REFERENCE_DIR, STYLE_DIR, PROJ_DIR]:
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

        self.btn_run = ttk.Button(self.root, text="开始提取高频词", command=self.start_processing)
        self.btn_run.pack(pady=10)

        self.log_text = tk.Text(self.root, height=8, width=65, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。已启用流式分块统计机制，保障低配机器的内存安全。")

    def toggle_entry(self):
        self.entry_manual.config(state="normal" if self.top_n_mode.get() == 2 else "disabled")

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def select_file(self):
        init_dir = REFERENCE_DIR if os.path.exists(REFERENCE_DIR) else BASE_DIR
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
            content = smart_read_text(file_path)
            novel_name = os.path.splitext(os.path.basename(file_path))[0]
            out_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "statistics")
            os.makedirs(out_dir, exist_ok=True)

            self.log(f"开始提取《{novel_name}》的高频词...")
            report = []
            
            # 【核心优化】：分块提取替代全量提取
            chunk_size = 50000
            word_counts = Counter()
            total_valid_count = 0
            
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i+chunk_size]
                chunk_valid_words = []
                for w in jieba.cut(chunk):
                    w = w.strip()
                    if w and w not in PUNCTUATIONS:
                        chunk_valid_words.append(w)
                word_counts.update(chunk_valid_words)
                total_valid_count += len(chunk_valid_words)
            
            if total_valid_count <= 1:
                self.log("文本过少，无法提取。")
                return

            if self.top_n_mode.get() == 1:
                unique = len(word_counts)
                log_ttr = math.log10(unique) / math.log10(total_valid_count) if total_valid_count > 1 else 0
                calc_n = int(50 * log_ttr * (total_valid_count ** (1/3.0))) if total_valid_count > 1 else 100
                top_n = max(100, min(8000, calc_n))
                self.log(f"动态算法建议提取量: Top {top_n}")
            else:
                top_n = int(self.manual_var.get())
                self.log(f"手动提取量: Top {top_n}")

            counts = word_counts.most_common(top_n)
            report.append(f"【高频词列表 (提取前 {top_n} 个)】\n" + "-"*40)
            
            for i in range(0, len(counts), 5):
                chunk = counts[i:i + 5]
                report.append("  ".join([f"{w}({c})" for w, c in chunk]))

            save_path = os.path.join(out_dir, "高频词.txt")
            atomic_write(save_path, "\n".join(report), data_type='text')

            self.log(f"[INFO] 提取完成！已保存至: {save_path}")
        except Exception as e:
            self.log(f"错误: {str(e)}")
        finally:
            self.btn_run.config(state="normal")

def run_headless(target_file):
    import sys
    if not os.path.exists(target_file):
        sys.exit(1)
        
    content = smart_read_text(target_file)
    novel_name = os.path.splitext(os.path.basename(target_file))[0]
    out_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "statistics")
    os.makedirs(out_dir, exist_ok=True)

    # 【核心优化】：静默模式同样应用分块与生成器更新
    chunk_size = 50000
    word_counts = Counter()
    total_valid_count = 0
    
    for i in range(0, len(content), chunk_size):
        chunk = content[i:i+chunk_size]
        chunk_valid_words = []
        for w in jieba.cut(chunk):
            w = w.strip()
            if w and w not in PUNCTUATIONS:
                chunk_valid_words.append(w)
        word_counts.update(chunk_valid_words)
        total_valid_count += len(chunk_valid_words)

    if total_valid_count <= 1: 
        sys.exit(0)

    unique = len(word_counts)
    log_ttr = math.log10(unique) / math.log10(total_valid_count) if total_valid_count > 1 else 0
    top_n = max(100, min(8000, int(50 * log_ttr * (total_valid_count ** (1/3.0)))))

    counts = word_counts.most_common(top_n)
    report = [f"【高频词列表 (提取前 {top_n} 个)】\n" + "-"*40]
    
    for i in range(0, len(counts), 5):
        chunk = counts[i:i + 5]
        report.append("  ".join([f"{w}({c})" for w, c in chunk]))

    save_path = os.path.join(out_dir, "高频词.txt")
    atomic_write(save_path, "\n".join(report), data_type='text')

if __name__ == "__main__":
    safe_run_app(app_class=WordFreqAnalyzerApp, headless_func=run_headless, target_file="")