# --- File: scripts/f5b_llm_novel_generation.py ---
import os
import random
import argparse
import threading
import re

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
from core._core_config import BASE_DIR, PROJECT_ROOT, PROJ_DIR
from core._core_utils import smart_read_text, atomic_write
from core._core_llm import stream_deepseek_api  

class NovelGenerationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f5b: 大模型正文流式生成引擎 (纯渲染版)")
        self.root.geometry("750x550")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        import tkinter as tk
        from tkinter import ttk
        padding = {'padx': 10, 'pady': 8}

        frame_base = ttk.LabelFrame(self.root, text="1. 目标定位 (执行前需确保 f5a 已生成大纲)")
        frame_base.pack(fill="x", **padding)
        
        ttk.Label(frame_base, text="目标项目名:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.project_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.project_var, width=25).grid(row=0, column=1, sticky="w", padx=5)
        
        ttk.Label(frame_base, text="本章章节名:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.chapter_name_var = tk.StringVar()
        ttk.Entry(frame_base, textvariable=self.chapter_name_var, width=25).grid(row=1, column=1, sticky="w", padx=5)

        frame_model = ttk.LabelFrame(self.root, text="2. 生成参数")
        frame_model.pack(fill="x", **padding)
        
        ttk.Label(frame_model, text="推理模型:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Radiobutton(frame_model, text="DeepSeek V3 (标准)", variable=self.model_var, value="deepseek-chat").grid(row=0, column=1, sticky="w", padx=10)
        ttk.Radiobutton(frame_model, text="DeepSeek R1 (推理)", variable=self.model_var, value="deepseek-reasoner").grid(row=0, column=2, sticky="w", padx=10)
        
        self.btn_process = ttk.Button(self.root, text="执行正文流式生成", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=15, width=95, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 10))
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。已接入 core 层的流式驱动。等待数据返回...")

    def log(self, message, append=False):
        import tkinter as tk
        self.log_text.config(state="normal")
        if append:
            self.log_text.insert(tk.END, message)
        else:
            self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def start_process_thread(self):
        import tkinter.messagebox as messagebox
        project_name = self.project_var.get().strip()
        chapter_name = self.chapter_name_var.get().strip()
        
        if not project_name or not chapter_name:
            messagebox.showwarning("提示", "项目名和章节名为必填项！")
            return
            
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, args=(project_name, chapter_name), daemon=True).start()

    def process_logic(self, project_name, chapter_name):
        model = self.model_var.get()
        self.execute_generation(project_name, chapter_name, model, self.log)
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
    def get_chapter_number(name):
        """智能提取文件名中的数字序列，支持阿拉伯数字和规范的中文数字 (位值累加解析版)"""
        import re
        arabic_match = re.search(r'\d+', name)
        if arabic_match:
            return int(arabic_match.group(0))
            
        cn_match = re.search(r'第([零一二两三四五六七八九十百千万]+)[章回节卷]', name)
        if cn_match:
            cn_num = cn_match.group(1)
            cn_map = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
            cn_units = {'十': 10, '百': 100, '千': 1000, '万': 10000}
             
            result = 0
            tmp = 0
            for char in cn_num:
                if char in cn_units:
                    unit = cn_units[char]
                    if tmp == 0 and unit == 10:
                        tmp = 1
                    result += tmp * unit
                    tmp = 0
                else:
                    tmp = cn_map.get(char, 0)
            result += tmp
            return result
             
        # 解析失败的兜底安全值，确保错误章节名排序沉底 
        return 999999

    @staticmethod
    def get_previous_context(content_dir, current_chapter_name):
        """【优化】基于文件名的正则语义排序提取，免疫文件系统时间戳篡改"""
        if not os.path.exists(content_dir):
            return "无前文记录。"
            
        chapters = [f for f in os.listdir(content_dir) if f.endswith(".txt")]
        if not chapters:
            return "无前文记录。"
            
        current_num = NovelGenerationApp.get_chapter_number(current_chapter_name)
        
        # 严格过滤出序号小于当前章节的历史章节
        prev_chapters = [f for f in chapters if NovelGenerationApp.get_chapter_number(f) < current_num]
        if not prev_chapters:
            return "无前文记录。"
            
        # 根据章节序号倒序排列，取最临近的上一章
        prev_chapters.sort(key=NovelGenerationApp.get_chapter_number, reverse=True)
        last_chapter_path = os.path.join(content_dir, prev_chapters[0])
        
        content = NovelGenerationApp.read_file_safe(last_chapter_path)
        return content[-1000:] if len(content) > 1000 else content

    @staticmethod
    def get_filtered_characters(target_dir, text_to_scan, log_func):
        """
        【新增修复】：在正文生成阶段，动态扫描大纲，重新加载本章出场的角色卡片
        """
        char_dir = os.path.join(target_dir, "character_profiles")
        if not os.path.exists(char_dir):
            return "无相关角色卡数据。"
        
        all_char_files = [f for f in os.listdir(char_dir) if f.endswith(".md")]
        relevant_texts = []
        found_names = []

        for f_name in all_char_files:
            char_name_base = os.path.splitext(f_name)[0]
            # 扫描大纲中是否提及该角色名
            if char_name_base in text_to_scan:
                content = NovelGenerationApp.read_file_safe(os.path.join(char_dir, f_name))
                if content:
                    relevant_texts.append(content)
                    found_names.append(char_name_base)
        
        if not relevant_texts:
            log_func("[WARN] 未在大纲中检测到特定角色名，将跳过角色卡深度注入（仅依赖世界观）。")
            return "本章节未提及特定已知角色卡中的人物。"
        
        log_func(f"[INFO] 成功为正文生成注入本章出场角色卡: {', '.join(found_names)}。")
        return "\n\n---\n\n".join(relevant_texts)

    @staticmethod
    def shuffle_paragraph_text(text):
        """
        【安全乱序版】：正则提取前/后缀 -> 局部词汇清洗 -> 乱序 -> 无损重组
        """
        if not text or not text.strip():
            return text

        # 快速判定：如果没有顿号，说明不是词汇列表段落，直接放行
        if '、' not in text:
            return text

        prefix = ""
        content = text
        suffix = ""

        # 定位前缀：兼容中英文冒号，保留 Markdown 语法（如 "- **外貌**："）
        match_prefix = re.search(r'^(.*?[:：])(.*)$', text)
        if match_prefix:
            prefix = match_prefix.group(1)
            content = match_prefix.group(2)

        # 定位后缀：剥离句末的句号、空白符等，避免乱序时句末标点跑到句中
        match_suffix = re.search(r'([。.\s]+)$', content)
        if match_suffix:
            suffix = match_suffix.group(1)
            content = content[:-len(suffix)]

        # 核心清洗与乱序
        words = content.split('、')
        clean_words = []
        for w in words:
            cw = w.strip()  # 局部清洗：仅去除词首尾的非法空白与隐形换行
            if cw:
                clean_words.append(cw)

        # 执行乱序并重组
        if len(clean_words) > 1:
            random.shuffle(clean_words)
            return f"{prefix}{'、'.join(clean_words)}{suffix}"

        return text

    @staticmethod
    def execute_generation(project_name, chapter_name, model, log_func, export_prompt_only=False):
        target_dir = os.path.join(PROJ_DIR, project_name)
        if not os.path.exists(target_dir):
            log_func(f"[ERROR] 错误: 未找到项目目录 {target_dir}")
            return False

        # 1. 载入核心大纲
        outline_path = os.path.join(target_dir, "chapter_structures", f"{chapter_name}_outline.md")
        chapter_outline = NovelGenerationApp.read_file_safe(outline_path)
        if not chapter_outline:
            log_func(f"[ERROR] 错误: 未找到本章大纲文件 {outline_path}，请先执行 f5a。")
            return False

        # 2. 载入世界观与角色卡 (【修复点】：解决模型“瞎写”人设的问题)
        log_func("正在加载世界观与本章角色设定...")
        world_settings = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "world_settings.md")) or "无详细世界观。"
        characters_info = NovelGenerationApp.get_filtered_characters(target_dir, chapter_outline, log_func)

        # 3. 载入文风与词库特征
        log_func("正在加载基础文风特征库...")
        features = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "features.md")) or "无特定文风描述。"
        
        positive_words_raw = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "positive_words.md")) or "无特定正面词汇。"
        if positive_words_raw != "无特定正面词汇。":
            shuffled_lines = []
            for line in positive_words_raw.split('\n'):
                shuffled_lines.append(NovelGenerationApp.shuffle_paragraph_text(line))
            positive_words = '\n'.join(shuffled_lines)
        else:
            positive_words = positive_words_raw
            
        negative_words = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "negative_words.md")) or "无特定负面词汇。"
        
        # 4. 重新组装极度严密的 System Prompt (整合所有设定规则)
        system_prompt = f"""你是一个专业的网络小说作家。你的任务是严格按照用户提供的【本章执行大纲】进行正文扩写，并完美符合给定的【世界观】、【人物设定】与【文风特征】。

【核心约束】：
1. 剧情执行：必须且只能写大纲规定的剧情，严禁自行跳跃大纲或发散额外的剧情。严禁改变人物的核心性格与行为逻辑。
2. 形式模仿：大纲末尾提供的“检索原文参考”（如果有）仅供学习其遣词造句、句子节奏与环境渲染语调。绝对禁止将原文参考中的具体剧情、事件代入本章正文中。
3. 文本排版：遵循网络小说排版规范，多换行，人物对话独立成段。字数要求在 3000 字左右。
4. 格式输出：直接开始输出小说正文，严禁输出任何形式的解释说明、结构标题或多余的寒暄语。

【底层设定与规则库】：

[世界观与底层设定]
{world_settings}

[本章出场角色卡]
{characters_info}

[文风特征]
{features}

[正向词汇偏好]
{positive_words}

[负向禁用词汇]
{negative_words}
"""

        # 5. 提取上下文衔接
        log_func("正在提取上下文接榫点数据...")
        content_dir = os.path.join(target_dir, "content")
        os.makedirs(content_dir, exist_ok=True)
        previous_context = NovelGenerationApp.get_previous_context(content_dir, chapter_name)

        user_prompt = f"""【前文回顾】（请无缝承接以下段落的物理动作或对话）：
{previous_context}

【本章执行大纲】（含本章必须执行的剧情细节与供模仿的原文参考）：
{chapter_outline}

请开始生成本章正文：
"""

        # 若是导出模式，直接输出到标准输出供 main.py 捕获，不执行 API
        if export_prompt_only:
            print(f"=== System Prompt ===\n{system_prompt}\n\n=== User Prompt ===\n{user_prompt}")
            return True

        prompt_dir = os.path.join(target_dir, "chapter_specific_prompts")
        os.makedirs(prompt_dir, exist_ok=True)
        prompt_filepath = os.path.join(prompt_dir, f"prompt_{chapter_name}.txt")
        
        try:
            prompt_content = f"=== System Prompt ===\n{system_prompt}\n\n=== User Prompt ===\n{user_prompt}\n"
            atomic_write(prompt_filepath, prompt_content, data_type='text')
            log_func(f"已将本章最终指令(含打乱词汇与人设库)原子级保存至: {prompt_filepath}")
        except Exception as e:
            log_func(f"保存指令文件失败: {str(e)}")

        log_func("\n>> 提示词构建完毕，正在通过 core 模块连接大模型执行流式生成...\n")
        output_filepath = os.path.join(content_dir, f"{chapter_name}.txt")
        
        try:
            full_content = ""
            # 调用流式引擎
            for chunk in stream_deepseek_api(system_prompt, user_prompt, model, temperature=0.5):
                log_func(chunk, append=True)
                full_content += chunk
            
            atomic_write(output_filepath, full_content, data_type='text')
            log_func(f"\n\n[INFO] 章节正文生成完毕！物理文件已原子级落盘至: {output_filepath}")
            return True
        except Exception as e:
            log_func(f"\n[ERROR] 流式生成中断或失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(project_name, chapter_name, model="deepseek-chat", export_prompt_only=False):
    import sys
    if not project_name or not chapter_name:
        print("error: 缺少项目名或章节名参数")
        sys.exit(1)
        
    if not export_prompt_only:
        print(f"开始静默执行小说流式生成: 项目 [{project_name}] - 章节 [{chapter_name}]")
        
    success = NovelGenerationApp.execute_generation(
        project_name, 
        chapter_name, 
        model, 
        lambda msg, append=False: print(msg, end="" if append else "\n", flush=True) if not export_prompt_only else None,
        export_prompt_only=export_prompt_only
    )
    if not success: sys.exit(1)

if __name__ == "__main__":
    safe_run_app(
        app_class=NovelGenerationApp,
        headless_func=run_headless,
        project_name="",
        chapter_name="",
        model=""
    )