import jieba
import jieba.posseg as pseg
import os
import re
from collections import Counter
import statistics
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import math

# --- 核心路径动态配置 ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, "reference_novels")
OUTPUT_DIR = os.path.join(BASE_DIR, "text_statistics")

# 仅保留标点符号和空白字符的过滤
PUNCTUATIONS = set("，。！？；：“”‘’（）【】《》、\n\r \t.!?,-[]")

class NovelMetricsAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("小说多维指标统合分析工具 (科学算法升级版)")
        self.root.geometry("620x680")
        self.root.resizable(False, False)

        self.ensure_directories()
        self.create_widgets()

    def ensure_directories(self):
        for directory in [INPUT_DIR, OUTPUT_DIR]:
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                except Exception as e:
                    print(f"创建目录失败: {directory}, 错误: {e}")

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        # --- 1. 文件选择区 ---
        frame_file = ttk.LabelFrame(self.root, text="1. 选择小说源文件 (reference_novels)")
        frame_file.pack(fill="x", **padding)

        self.file_path_var = tk.StringVar()
        entry_file = ttk.Entry(frame_file, textvariable=self.file_path_var, state="readonly", width=55)
        entry_file.grid(row=0, column=0, padx=5, pady=10)

        btn_browse = ttk.Button(frame_file, text="浏览...", command=self.select_file)
        btn_browse.grid(row=0, column=1, padx=5, pady=10)

        # --- 2. 高频词提取参数设置区 ---
        frame_settings = ttk.LabelFrame(self.root, text="2. 高频词提取策略 (长文本立方根优化版)")
        frame_settings.pack(fill="x", **padding)

        self.top_n_mode = tk.IntVar(value=1)
        
        rb_auto = ttk.Radiobutton(frame_settings, text="智能动态推荐 (基于立方根与对数TTR算法)", variable=self.top_n_mode, value=1, command=self.toggle_top_n_entry)
        rb_auto.grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        
        # 更新了面板上的公式说明
        ttk.Label(frame_settings, text=" * 公式: N = 50 × (对数TTR) × ∛有效词数\n * 原理: 适配 Heaps 定律，防止超长文本提取量爆炸 (上限 8000)", foreground="gray").grid(row=1, column=0, columnspan=2, sticky="w", padx=25)

        rb_manual = ttk.Radiobutton(frame_settings, text="手动指定提取前 N 个:", variable=self.top_n_mode, value=2, command=self.toggle_top_n_entry)
        rb_manual.grid(row=2, column=0, sticky="w", padx=5, pady=5)

        self.manual_top_n_var = tk.StringVar(value="500")
        self.entry_manual_n = ttk.Entry(frame_settings, textvariable=self.manual_top_n_var, state="disabled", width=10)
        self.entry_manual_n.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # --- 3. 执行与日志区 ---
        frame_run = ttk.Frame(self.root)
        frame_run.pack(fill="x", **padding)

        self.btn_run = ttk.Button(frame_run, text="▶ 开始综合分析并生成专属文件夹", command=self.start_processing)
        self.btn_run.pack(pady=5)

        self.log_text = tk.Text(self.root, height=14, width=80, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log(f"系统就绪。\n工作区目录定位成功：{BASE_DIR}")
        self.log("分析结果将自动按【小说名_统计】的格式分文件夹保存。")

    def toggle_top_n_entry(self):
        if self.top_n_mode.get() == 2:
            self.entry_manual_n.config(state="normal")
        else:
            self.entry_manual_n.config(state="disabled")

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def select_file(self):
        init_dir = INPUT_DIR if os.path.exists(INPUT_DIR) else BASE_DIR
        file_path = filedialog.askopenfilename(
            initialdir=init_dir,
            title="请选择小说文件",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.log(f"已选择: {os.path.basename(file_path)}")

    def start_processing(self):
        file_path = self.file_path_var.get()
        if not file_path:
            messagebox.showwarning("警告", "请先选择小说源文件！")
            return

        if self.top_n_mode.get() == 2:
            try:
                manual_n = int(self.manual_top_n_var.get().strip())
                if manual_n <= 0: raise ValueError
            except ValueError:
                messagebox.showwarning("警告", "手动提取名次必须是一个正整数！")
                return

        self.btn_run.config(state="disabled")
        self.log("-" * 40)
        threading.Thread(target=self.run_analysis, args=(file_path,), daemon=True).start()

    def run_analysis(self, file_path):
        try:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='gbk') as f:
                    content = f.read()

            novel_name = os.path.splitext(os.path.basename(file_path))[0]
            
            novel_output_dir = os.path.join(OUTPUT_DIR, f"{novel_name}_统计")
            if not os.path.exists(novel_output_dir):
                os.makedirs(novel_output_dir)

            self.log(f"开始分析《{novel_name}》...")
            
            metrics_report = []
            words_report = []

            self.log(">> 正在计算句子与段落长度指标...")
            self.calc_length_metrics(content, metrics_report)

            self.log(">> 正在统计标点符号分布...")
            self.calc_punctuation_metrics(content, metrics_report)

            self.log(">> 正在分析对话提示语结构...")
            self.calc_dialogue_metrics(content, metrics_report)

            self.log(">> 正在提取高频词并计算核心丰富度 (生成第四节报告)...")
            self.calc_high_freq_words(content, metrics_report, words_report)

            # 移除了 20 万字的样本限制，改为全量扫描
            self.log(">> 正在进行全量 NLP 词性分布扫描 (大文本耗时较长，请耐心等待)...")
            self.calc_pos_distribution(content, metrics_report)

            metrics_path = os.path.join(novel_output_dir, "统计指标.txt")
            words_path = os.path.join(novel_output_dir, "高频词.txt")
            
            with open(metrics_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(metrics_report))
                
            with open(words_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(words_report))

            self.log(f"\n✅ 分析完成！")
            self.log(f"已生成文件夹: {novel_output_dir}")

        except Exception as e:
            self.log(f"发生错误: {str(e)}")
            messagebox.showerror("错误", f"发生异常:\n{str(e)}")
        finally:
            self.btn_run.config(state="normal")

    def calc_length_metrics(self, content, report):
        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
        sentences = [s.strip() for s in re.split(r'[。！？.!?]+', content) if s.strip()]
        clauses = [c.strip() for c in re.split(r'[，。！？；,.!?;]+', content) if c.strip()]

        def get_stats(data):
            if not data: return 0, 0
            lengths = [len(x) for x in data]
            avg = statistics.mean(lengths)
            var = statistics.pstdev(lengths)
            return avg, var

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
        if total_punc == 0 or total_chars == 0:
            report.append("未检测到有效标点符号。\n")
            return

        punc_counts = Counter(punctuations)
        report.append(f"总字数(含符号)：{total_chars} | 符号总数：{total_punc}")
        report.append(f"符号密度(符号总数/总字数)：{(total_punc / total_chars) * 100:.2f}%")
        report.append("常见符号内部占比(Top 10)：")
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

        total_tags = front + mid + rear + none
        if total_tags == 0: total_tags = 1

        report.append("【三、 对话结构偏好分析】")
        report.append(f"双引号出现频率：共 {total_quotes} 次")
        report.append(f"引号内平均字数：{avg_quote_len:.2f} 字")
        report.append("提示语位置偏好占比 (基于段落估算)：")
        report.append(f"- 前置 (某某说：“...”): {front} 次 ({front / total_tags * 100:.1f}%)")
        report.append(f"- 中置 (“...”，某某说，“...”): {mid} 次 ({mid / total_tags * 100:.1f}%)")
        report.append(f"- 后置 (“...”，某某说。): {rear} 次 ({rear / total_tags * 100:.1f}%)")
        report.append(f"- 无提示语 (纯对话连贯): {none} 次 ({none / total_tags * 100:.1f}%)\n")

    def calc_high_freq_words(self, content, metrics_report, words_report):
        words = jieba.lcut(content)
        valid_words = [w for w in words if w.strip() and w not in PUNCTUATIONS]
        
        total_valid = len(valid_words)
        unique_words = len(set(valid_words))
        
        if total_valid <= 1:
            words_report.append("文本无效或字数过少，无法提取词汇。")
            return

        # 1. 对数 TTR (Herdan's C) 
        log_ttr = math.log10(unique_words) / math.log10(total_valid)
        # 2. 根号 TTR (Guiraud's Index)
        root_ttr = unique_words / math.sqrt(total_valid)
        # 3. 基础重复率
        naive_repetition_rate = 1.0 - (unique_words / total_valid)
        
        # 将体检指标归拢至 metrics_report (统计指标.txt) 中
        metrics_report.append("【四、 词汇丰富度指标】")
        metrics_report.append(f"有效总词数(Tokens): {total_valid} | 独立词汇数(Types): {unique_words}")
        metrics_report.append(f"- 对数 TTR (Herdan's C): {log_ttr:.4f} (推荐参考，越接近1代表词汇越丰富)")
        metrics_report.append(f"- 根号 TTR (Guiraud's Index): {root_ttr:.2f} (常数指标，同等体量下越大越好)")
        metrics_report.append(f"- 基础篇幅重复率: {naive_repetition_rate * 100:.2f}%\n")

        # 确定需要提取的 Top N 数量，采用 k * C * (N^(1/3)) 公式
        if self.top_n_mode.get() == 1:
            # 引入系数 k=50，并使用立方根对齐大文本长尾特征
            calculated_n = int(50 * log_ttr * (total_valid ** (1/3.0)))
            # 设置硬性上限 8000
            top_n = max(100, min(8000, calculated_n))
            self.log(f"  -> 结合立方根算法得出建议提取量: Top {top_n}")
        else:
            top_n = int(self.manual_top_n_var.get().strip())
            self.log(f"  -> 手动设定提取量: Top {top_n}")

        counts = Counter(valid_words).most_common(top_n)

        # 仅输出纯净的高频词列表到 words_report
        words_report.append(f"【高频词列表 (提取前 {top_n} 个)】")
        words_report.append("-" * 40)
        
        for i in range(0, len(counts), 5):
            chunk = counts[i:i + 5]
            line = "  ".join([f"{w}({c})" for w, c in chunk])
            words_report.append(line)

    def calc_pos_distribution(self, content, report):
        # 取消前 20 万字限制，全量扫描以保证整体准确性
        words = pseg.cut(content)

        pos_counter = Counter()
        total_valid_words = 0

        for w, flag in words:
            if not w.strip() or w in PUNCTUATIONS: continue
            if flag.startswith('n'): pos_counter['名词'] += 1
            elif flag.startswith('v'): pos_counter['动词'] += 1
            elif flag.startswith('a'): pos_counter['形容词'] += 1
            elif flag.startswith('d'): pos_counter['副词'] += 1
            elif flag.startswith('r'): pos_counter['代词 (我/你/他/这等)'] += 1
            elif flag.startswith('u'): pos_counter['助词 (的/了/着等)'] += 1
            elif flag.startswith('p'): pos_counter['介词'] += 1
            elif flag.startswith('c'): pos_counter['连词'] += 1
            elif flag.startswith('m') or flag.startswith('q'): pos_counter['数量词'] += 1
            else: pos_counter['其他'] += 1
            total_valid_words += 1

        if total_valid_words == 0: total_valid_words = 1

        report.append("【五、 宏观词性分布比例】")
        report.append("(注：基于全文本量样本分析)")
        for pos, count in pos_counter.most_common():
            report.append(f"  {pos} : {count / total_valid_words * 100:.2f}%")
        report.append("")

if __name__ == "__main__":
    root = tk.Tk()
    app = NovelMetricsAnalyzerApp(root)
    root.mainloop()