# --- File: scripts/f1a_local_text_stats.py ---
import os
import re
import shutil
import math
import statistics
from collections import Counter
import threading
import argparse

import jieba
import jieba.posseg as pseg

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
# 2. 导入 core 模块
# =====================================================================
from core._core_config import BASE_DIR, PROJECT_ROOT, REFERENCE_DIR, STYLE_DIR, PROJ_DIR
from core._core_utils import smart_read_text, atomic_write

PUNCTUATIONS = set("，。！？；：“”‘’（）【】《》、\n\r \t.!?,-[]")

class WelfordStats:
    """
    Welford's Online Algorithm (流式统计算法)
    用于在不保存全量数组的情况下，动态且极低内存地计算样本的数量、平均值与总体标准差。
    """
    def __init__(self):
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, val):
        self.count += 1
        delta = val - self.mean
        self.mean += delta / self.count
        delta2 = val - self.mean
        self.m2 += delta * delta2

    def variance(self):
        if self.count < 1: 
            return 0.0
        return self.m2 / self.count

    def std_dev(self):
        return math.sqrt(self.variance())

class NovelMetricsAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f1a: 文本物理指标与TTR统计 (低内存流式处理版)")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        self.ensure_directories()
        self.create_widgets()

    def ensure_directories(self):
        for directory in [REFERENCE_DIR, STYLE_DIR, PROJ_DIR]:
            os.makedirs(directory, exist_ok=True)

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}
        frame_file = ttk.LabelFrame(self.root, text="选择小说源文件 (reference_novels)")
        frame_file.pack(fill="x", **padding)

        self.file_path_var = tk.StringVar()
        ttk.Entry(frame_file, textvariable=self.file_path_var, state="readonly", width=55).grid(row=0, column=0, padx=5, pady=10)
        ttk.Button(frame_file, text="浏览...", command=self.select_file).grid(row=0, column=1, padx=5, pady=10)

        self.btn_run = ttk.Button(self.root, text="开始计算物理指标与TTR", command=self.start_processing)
        self.btn_run.pack(pady=10)

        self.log_text = tk.Text(self.root, height=12, width=75, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log(f"系统就绪。\n工作区目录定位成功：{PROJECT_ROOT}")

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def select_file(self):
        init_dir = REFERENCE_DIR if os.path.exists(REFERENCE_DIR) else BASE_DIR
        path = filedialog.askopenfilename(initialdir=init_dir, title="选择小说文件", filetypes=[("Text Files", "*.txt")])
        if path:
            self.file_path_var.set(path)
            self.log(f"已选择: {os.path.basename(path)}")

    def start_processing(self):
        if not self.file_path_var.get():
            messagebox.showwarning("警告", "请先选择小说源文件！")
            return
        self.btn_run.config(state="disabled")
        threading.Thread(target=self.run_analysis, args=(self.file_path_var.get(),), daemon=True).start()

    def run_analysis(self, file_path):
        try:
            content = smart_read_text(file_path)
            novel_name = os.path.splitext(os.path.basename(file_path))[0]
            
            style_novel_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
            os.makedirs(style_novel_dir, exist_ok=True)
            
            ref_path = os.path.join(style_novel_dir, "reference.txt")
            if not os.path.exists(ref_path):
                shutil.copy2(file_path, ref_path)
                self.log(">> 已自动备份原文至 reference.txt")

            out_dir = os.path.join(style_novel_dir, "statistics")
            os.makedirs(out_dir, exist_ok=True)

            self.log(f"开始分析《{novel_name}》物理指标...")
            report = []
            
            self.log(">> 正在计算句子与段落长度指标 (流式精准正则防OOM)...")
            self.calc_length_metrics(content, report)
            self.log(">> 正在统计标点符号分布...")
            self.calc_punctuation_metrics(content, report)
            self.log(">> 正在分析对话提示语结构...")
            self.calc_dialogue_metrics(content, report)
            self.log(">> 正在计算TTR与词汇丰富度 (分块处理)...")
            self.calc_ttr_metrics(content, report)
            self.log(">> 正在进行全量NLP词性分布扫描 (分块处理)...")
            self.calc_pos_distribution(content, report)

            save_path = os.path.join(out_dir, "统计指标.txt")
            atomic_write(save_path, "\n".join(report), data_type='text')

            self.log(f"\n[INFO] 指标计算完成！文件保存至: {save_path}")
        except Exception as e:
            self.log(f"错误: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.btn_run.config(state="normal")

    def calc_length_metrics(self, content, report):
        p_stats = WelfordStats()
        s_stats = WelfordStats()
        c_stats = WelfordStats()
        
        # 优化方案A：基于前后向断言的精准正则 (Context-Aware Regex)
        # 解释：中文标点直接切分；英文标点仅在其前后并非数字时切分，完美避开如 "3.14"、"1,000" 等浮点数和千分位引发的误切
        s_pattern = re.compile(r'[。！？]+|(?<!\d)[.!?]+(?!\d)')
        c_pattern = re.compile(r'[，。！？；]+|(?<!\d)[.,!?;]+(?!\d)')
        
        # 优化方案A：基于 Welford 算法流式处理 (防 OOM 内存爆炸与数组瞬间膨胀)
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # 段落长度动态更新
            p_stats.update(len(line))
            
            # 完整句（长句）长度动态更新
            start = 0
            for match in s_pattern.finditer(line):
                segment = line[start:match.start()].strip()
                if segment:
                    s_stats.update(len(segment))
                start = match.end()
            if start < len(line):
                segment = line[start:].strip()
                if segment:
                    s_stats.update(len(segment))
                    
            # 短句（断句）长度动态更新
            start = 0
            for match in c_pattern.finditer(line):
                segment = line[start:match.start()].strip()
                if segment:
                    c_stats.update(len(segment))
                start = match.end()
            if start < len(line):
                segment = line[start:].strip()
                if segment:
                    c_stats.update(len(segment))
        
        report.append("【一、 文本骨架长度统计】")
        report.append(f"段落总数：{p_stats.count} 段")
        report.append(f"- 平均段落长度：{p_stats.mean:.2f} 字 (标准差: {p_stats.std_dev():.2f})")
        report.append(f"- 平均完整句长度：{s_stats.mean:.2f} 字 (标准差: {s_stats.std_dev():.2f})")
        report.append(f"- 平均断句(单句)长度：{c_stats.mean:.2f} 字 (标准差: {c_stats.std_dev():.2f})\n")

    def calc_punctuation_metrics(self, content, report):
        punc_counts = Counter(c for c in content if c in PUNCTUATIONS and re.match(r'[，。！？；：“”‘’（）《》、\.\,\?\!\:\;\-\[\]]', c))
        total_punc = sum(punc_counts.values())
        total_chars = len(content)
        
        report.append("【二、 标点符号使用率】")
        if total_punc == 0:
            report.append("未检测到有效标点。\n")
            return
            
        report.append(f"总字数(含符号)：{total_chars} | 符号总数：{total_punc}")
        report.append(f"符号密度：{(total_punc / total_chars) * 100:.2f}%")
        report.append("常见符号占比(Top 10)：")
        for p, count in punc_counts.most_common(10):
            report.append(f"  {p} : {count} 次 ({count / total_punc * 100:.2f}%)")
        report.append("")

    def calc_dialogue_metrics(self, content, report):
        quotes_iter = re.finditer(r'“([^”]*)”', content)
        quote_lengths = [len(m.group(1)) for m in quotes_iter]
        total_quotes = len(quote_lengths)
        
        if total_quotes == 0:
            report.append("【三、 对话结构偏好分析】\n未检测到双引号。\n")
            return
            
        avg_quote_len = statistics.mean(quote_lengths)
        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
        front, mid, rear, none = 0, 0, 0, 0
        speak_verbs = ['说', '道', '问', '答', '叹', '喊', '吼', '笑']
        
        for p in paragraphs:
            q_in_p = re.findall(r'“([^”]*)”', p)
            if not q_in_p: continue
            has_verb = any(v in p for v in speak_verbs)
            if len(q_in_p) == 1:
                if p.startswith('“') and p.endswith('”') and not has_verb: none += 1
                elif p.endswith('”') and has_verb: front += 1
                elif p.startswith('“') and has_verb: rear += 1
                else: none += 1
            elif len(q_in_p) >= 2:
                if has_verb: mid += 1
                else: none += 1
                
        total_tags = front + mid + rear + none or 1
        report.append("【三、 对话结构偏好分析】")
        report.append(f"双引号频率：共 {total_quotes} 次")
        report.append(f"引号内平均字数：{avg_quote_len:.2f} 字")
        report.append(f"- 前置: {front} 次 ({front / total_tags * 100:.1f}%)")
        report.append(f"- 中置: {mid} 次 ({mid / total_tags * 100:.1f}%)")
        report.append(f"- 后置: {rear} 次 ({rear / total_tags * 100:.1f}%)")
        report.append(f"- 无提示语: {none} 次 ({none / total_tags * 100:.1f}%)\n")

    def calc_ttr_metrics(self, content, report):
        chunk_size = 50000 
        unique_words = set()
        total_valid = 0
        
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i+chunk_size]
            for w in jieba.cut(chunk):
                w = w.strip()
                if w and w not in PUNCTUATIONS:
                    total_valid += 1
                    unique_words.add(w)

        report.append("【四、 词汇丰富度指标】")
        if total_valid <= 1:
            report.append("文本过少，无法统计。\n")
            return
            
        unique_count = len(unique_words)
        log_ttr = math.log10(unique_count) / math.log10(total_valid)
        root_ttr = unique_count / math.sqrt(total_valid)
        
        report.append(f"有效总词数(Tokens): {total_valid} | 独立词汇数(Types): {unique_count}")
        report.append(f"- 对数 TTR: {log_ttr:.4f}")
        report.append(f"- 根号 TTR: {root_ttr:.2f}")
        report.append(f"- 基础篇幅重复率: {(1.0 - (unique_count / total_valid)) * 100:.2f}%\n")

    def calc_pos_distribution(self, content, report):
        pos_counter = Counter()
        total = 0
        chunk_size = 50000
        
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i+chunk_size]
            for w, flag in pseg.cut(chunk):
                w = w.strip()
                if not w or w in PUNCTUATIONS: continue
                if flag.startswith('n'): pos_counter['名词'] += 1
                elif flag.startswith('v'): pos_counter['动词'] += 1
                elif flag.startswith('a'): pos_counter['形容词'] += 1
                elif flag.startswith('d'): pos_counter['副词'] += 1
                elif flag.startswith('r'): pos_counter['代词'] += 1
                elif flag.startswith('u'): pos_counter['助词'] += 1
                elif flag.startswith('p'): pos_counter['介词'] += 1
                elif flag.startswith('c'): pos_counter['连词'] += 1
                elif flag.startswith('m') or flag.startswith('q'): pos_counter['数量词'] += 1
                else: pos_counter['其他'] += 1
                total += 1
                
        total = total or 1
        report.append("【五、 宏观词性分布比例】")
        for pos, count in pos_counter.most_common():
            report.append(f"  {pos} : {count / total * 100:.2f}%")
        report.append("")

def run_headless(target_file):
    if not os.path.exists(target_file):
        import sys
        sys.exit(1)
    content = smart_read_text(target_file)

    novel_name = os.path.splitext(os.path.basename(target_file))[0]
    style_novel_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
    os.makedirs(style_novel_dir, exist_ok=True)
    
    ref_path = os.path.join(style_novel_dir, "reference.txt")
    if not os.path.exists(ref_path):
        shutil.copy2(target_file, ref_path)

    out_dir = os.path.join(style_novel_dir, "statistics")
    os.makedirs(out_dir, exist_ok=True)

    app = NovelMetricsAnalyzerApp.__new__(NovelMetricsAnalyzerApp)
    report = []
    app.calc_length_metrics(content, report)
    app.calc_punctuation_metrics(content, report)
    app.calc_dialogue_metrics(content, report)
    app.calc_ttr_metrics(content, report)
    app.calc_pos_distribution(content, report)

    save_path = os.path.join(out_dir, "统计指标.txt")
    atomic_write(save_path, "\n".join(report), data_type='text')

if __name__ == "__main__":
    safe_run_app(app_class=NovelMetricsAnalyzerApp, headless_func=run_headless, target_file="")