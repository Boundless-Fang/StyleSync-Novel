import sys
import argparse
import jieba
import jieba.posseg as pseg
import os
import re
import shutil
from collections import Counter
import statistics
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import math

# --- 物理目录严格对齐架构图 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
INPUT_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")

PUNCTUATIONS = set("，。！？；：“”‘’（）【】《》、\n\r \t.!?,-[]")

class NovelMetricsAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f1a: 文本物理指标与TTR统计 (GUI测试模式)")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        self.ensure_directories()
        self.create_widgets()

    def ensure_directories(self):
        for directory in [INPUT_DIR, STYLE_DIR, PROJ_DIR]:
            os.makedirs(directory, exist_ok=True)

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}
        frame_file = ttk.LabelFrame(self.root, text="选择小说源文件 (reference_novels)")
        frame_file.pack(fill="x", **padding)

        self.file_path_var = tk.StringVar()
        ttk.Entry(frame_file, textvariable=self.file_path_var, state="readonly", width=55).grid(row=0, column=0, padx=5, pady=10)
        ttk.Button(frame_file, text="浏览...", command=self.select_file).grid(row=0, column=1, padx=5, pady=10)

        self.btn_run = ttk.Button(self.root, text="▶ 开始计算物理指标与TTR", command=self.start_processing)
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
        init_dir = INPUT_DIR if os.path.exists(INPUT_DIR) else BASE_DIR
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
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='gbk') as f:
                    content = f.read()

            novel_name = os.path.splitext(os.path.basename(file_path))[0]
            
            # 严格对齐架构图：构建 text_style_imitation 下的专属文件夹
            style_novel_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
            os.makedirs(style_novel_dir, exist_ok=True)
            
            # 对齐架构图：自动拷贝原文作为 reference.txt
            ref_path = os.path.join(style_novel_dir, "reference.txt")
            if not os.path.exists(ref_path):
                shutil.copy2(file_path, ref_path)
                self.log(">> 已自动备份原文至 reference.txt")

            # 对齐架构图：结果放入 statistics 文件夹
            out_dir = os.path.join(style_novel_dir, "statistics")
            os.makedirs(out_dir, exist_ok=True)

            self.log(f"开始分析《{novel_name}》物理指标...")
            report = []
            
            self.log(">> 正在计算句子与段落长度指标...")
            self.calc_length_metrics(content, report)
            self.log(">> 正在统计标点符号分布...")
            self.calc_punctuation_metrics(content, report)
            self.log(">> 正在分析对话提示语结构...")
            self.calc_dialogue_metrics(content, report)
            self.log(">> 正在计算TTR与词汇丰富度...")
            self.calc_ttr_metrics(content, report)
            self.log(">> 正在进行全量NLP词性分布扫描...")
            self.calc_pos_distribution(content, report)

            save_path = os.path.join(out_dir, "统计指标.txt")
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(report))

            self.log(f"\n✅ 指标计算完成！文件保存至: {save_path}")
        except Exception as e:
            self.log(f"错误: {str(e)}")
        finally:
            self.btn_run.config(state="normal")

    def calc_length_metrics(self, content, report):
        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
        sentences = [s.strip() for s in re.split(r'[。！？.!?]+', content) if s.strip()]
        clauses = [c.strip() for c in re.split(r'[，。！？；,.!?;]+', content) if c.strip()]
        def get_stats(data):
            if not data: return 0, 0
            lengths = [len(x) for x in data]
            return statistics.mean(lengths), statistics.pstdev(lengths)
        p_avg, p_var = get_stats(paragraphs)
        s_avg, s_var = get_stats(sentences)
        c_avg, c_var = get_stats(clauses)
        report.append("【一、 文本骨架长度统计】")
        report.append(f"段落总数：{len(paragraphs)} 段")
        report.append(f"- 平均段落长度：{p_avg:.2f} 字 (标准差: {p_var:.2f})")
        report.append(f"- 平均完整句长度：{s_avg:.2f} 字 (标准差: {s_var:.2f})")
        report.append(f"- 平均断句(单句)长度：{c_avg:.2f} 字 (标准差: {c_var:.2f})\n")

    def calc_punctuation_metrics(self, content, report):
        punctuations = re.findall(r'[，。！？；：“”‘’（）《》、\.\,\?\!\:\;\-\[\]]', content)
        total_punc = len(punctuations)
        total_chars = len(content)
        report.append("【二、 标点符号使用率】")
        if total_punc == 0:
            report.append("未检测到有效标点。\n")
            return
        punc_counts = Counter(punctuations)
        report.append(f"总字数(含符号)：{total_chars} | 符号总数：{total_punc}")
        report.append(f"符号密度：{(total_punc / total_chars) * 100:.2f}%")
        report.append("常见符号占比(Top 10)：")
        for p, count in punc_counts.most_common(10):
            report.append(f"  {p} : {count} 次 ({count / total_punc * 100:.2f}%)")
        report.append("")

    def calc_dialogue_metrics(self, content, report):
        quotes = re.findall(r'“([^”]*)”', content)
        total_quotes = len(quotes)
        if total_quotes == 0:
            report.append("【三、 对话结构偏好分析】\n未检测到双引号。\n")
            return
        avg_quote_len = statistics.mean([len(q) for q in quotes])
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
        words = jieba.lcut(content)
        valid_words = [w for w in words if w.strip() and w not in PUNCTUATIONS]
        total_valid = len(valid_words)
        unique_words = len(set(valid_words))
        report.append("【四、 词汇丰富度指标】")
        if total_valid <= 1:
            report.append("文本过少，无法统计。\n")
            return
        log_ttr = math.log10(unique_words) / math.log10(total_valid)
        root_ttr = unique_words / math.sqrt(total_valid)
        report.append(f"有效总词数(Tokens): {total_valid} | 独立词汇数(Types): {unique_words}")
        report.append(f"- 对数 TTR: {log_ttr:.4f}")
        report.append(f"- 根号 TTR: {root_ttr:.2f}")
        report.append(f"- 基础篇幅重复率: {(1.0 - (unique_words / total_valid)) * 100:.2f}%\n")

    def calc_pos_distribution(self, content, report):
        words = pseg.cut(content)
        pos_counter = Counter()
        total = 0                                           
        for w, flag in words:
            if not w.strip() or w in PUNCTUATIONS: continue
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
    style_novel_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
    os.makedirs(style_novel_dir, exist_ok=True)
    
    # 拷贝 reference
    ref_path = os.path.join(style_novel_dir, "reference.txt")
    if not os.path.exists(ref_path):
        shutil.copy2(file_path, ref_path)

    out_dir = os.path.join(style_novel_dir, "statistics")
    os.makedirs(out_dir, exist_ok=True)

    app = NovelMetricsAnalyzerApp.__new__(NovelMetricsAnalyzerApp)
    report = []
    app.calc_length_metrics(content, report)
    app.calc_punctuation_metrics(content, report)
    app.calc_dialogue_metrics(content, report)
    app.calc_ttr_metrics(content, report)
    app.calc_pos_distribution(content, report)

    with open(os.path.join(out_dir, "统计指标.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(report))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, default="")
    parser.add_argument("--project", type=str, default="") # 保留接收入口，但代码中不使用，避免main.py传参报错
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        root = tk.Tk()
        app = NovelMetricsAnalyzerApp(root)
        root.mainloop()
    else:
        if not args.target_file and unknown and not unknown[0].startswith('--'):
            args.target_file = unknown[0]
        # 静默模式不再传递 project_name
        run_headless(args.target_file)