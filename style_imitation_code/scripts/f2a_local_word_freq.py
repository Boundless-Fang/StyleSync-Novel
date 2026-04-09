import os
import math
from collections import Counter
import jieba

from core._core_gui_runner import safe_run_app, inject_env, ThreadSafeBaseGUI
inject_env()

from core._core_config import BASE_DIR, PROJECT_ROOT, REFERENCE_DIR, STYLE_DIR, PROJ_DIR
from core._core_utils import smart_yield_text, atomic_write

PUNCTUATIONS = set("，。！？；：“”‘’（）【】《》、\n\r \t.!?,-[]")

class WordFreqAnalyzerApp(ThreadSafeBaseGUI):
    def __init__(self, root):
        super().__init__(root, title="f2a: 本地高频词提取工具", geometry="520x450")

    def setup_custom_widgets(self):
        import tkinter as tk
        from tkinter import ttk, filedialog
        padding = {'padx': 10, 'pady': 8}

        for directory in [REFERENCE_DIR, STYLE_DIR, PROJ_DIR]:
            os.makedirs(directory, exist_ok=True)

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

        self.btn_run = ttk.Button(self.root, text="开始提取高频词", command=lambda: self.start_process_thread(self.btn_run))
        self.btn_run.pack(pady=10)

    def toggle_entry(self):
        self.entry_manual.config(state="normal" if self.top_n_mode.get() == 2 else "disabled")

    def select_file(self):
        import tkinter as tk
        from tkinter import filedialog
        init_dir = REFERENCE_DIR if os.path.exists(REFERENCE_DIR) else BASE_DIR
        path = filedialog.askopenfilename(initialdir=init_dir, title="选择原文", filetypes=[("Text Files", "*.txt")])
        if path: self.file_path_var.set(path)

    def execute_logic(self):
        import tkinter.messagebox as messagebox
        file_path = self.file_path_var.get()
        if not file_path:
            self.log("[ERROR] 请先选择小说源文件！")
            return
            
        if self.top_n_mode.get() == 2 and not self.manual_var.get().isdigit():
            self.log("[ERROR] 提取数量请输入正确的数字！")
            return

        try:
            novel_name = os.path.splitext(os.path.basename(file_path))[0]
            out_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "statistics")
            os.makedirs(out_dir, exist_ok=True)

            self.log(f"开始提取《{novel_name}》的高频词 (流式缓冲扫描)...")
            report = []
            
            word_counts = Counter()
            total_valid_count = 0
            
            for content_chunk in smart_yield_text(file_path):
                chunk_valid_words = []
                for w in jieba.cut(content_chunk):
                    w = w.strip()
                    if w and w not in PUNCTUATIONS:
                        chunk_valid_words.append(w)
                word_counts.update(chunk_valid_words)
                total_valid_count += len(chunk_valid_words)
            
            if total_valid_count <= 1:
                self.log("[WARN] 文本过少，无法提取。")
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

            self.log(f"[INFO] 提取完成！已原子级落盘至: {save_path}")
        except Exception as e:
            self.log(f"[ERROR] 错误: {str(e)}")

def run_headless(target_file):
    import sys
    if not os.path.exists(target_file):
        sys.exit(1)
        
    novel_name = os.path.splitext(os.path.basename(target_file))[0]
    out_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "statistics")
    os.makedirs(out_dir, exist_ok=True)

    word_counts = Counter()
    total_valid_count = 0
    
    for content_chunk in smart_yield_text(target_file):
        chunk_valid_words = []
        for w in jieba.cut(content_chunk):
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
