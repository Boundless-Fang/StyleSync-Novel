import os
import random
import argparse
import threading

# =====================================================================
# 1. 跨目录寻址：将父目录(style_imitation_code)加入环境变量
# =====================================================================
import sys
current_dir = os.path.dirname(os.path.abspath(__file__)) # 指向 scripts/
parent_dir = os.path.dirname(current_dir)                # 指向 style_imitation_code/
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# =====================================================================
# 2. 导入 core 模块 (注意加 core. 前缀)
# =====================================================================
from core._core_config import BASE_DIR, PROJECT_ROOT, PROJ_DIR
from core._core_utils import smart_read_text
from core._core_llm import stream_deepseek_api  

class NovelGenerationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f5b: 大模型正文流式生成引擎 (纯渲染版)")
        self.root.geometry("750x550")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
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
        
        self.btn_process = ttk.Button(self.root, text="▶ 执行正文流式生成", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=15, width=95, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 10))
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。已接入 core 层的流式驱动。等待数据返回...")

    def log(self, message, append=False):
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
    def get_previous_context(content_dir, current_chapter_name):
        if not os.path.exists(content_dir):
            return "无前文记录。"
            
        chapters = [f for f in os.listdir(content_dir) if f.endswith(".txt")]
        if not chapters:
            return "无前文记录。"
            
        chapters_paths = [os.path.join(content_dir, f) for f in chapters if f != f"{current_chapter_name}.txt"]
        if not chapters_paths:
            return "无前文记录。"
            
        chapters_paths.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        last_chapter_path = chapters_paths[0]
        
        content = NovelGenerationApp.read_file_safe(last_chapter_path)
        return content[-1000:] if len(content) > 1000 else content

    @staticmethod
    def shuffle_paragraph_text(text):
        if '、' not in text:
            return text

        prefix = ""
        content = text
        if '：' in text:
            parts = text.split('：', 1)
            if '、' in parts[1]:
                prefix = parts[0] + '：'
                content = parts[1]

        suffix = ""
        content = content.strip()
        if content.endswith('。'):
            suffix = "。"
            content = content[:-1]

        words = content.split('、')
        words = [w.strip() for w in words if w.strip()]

        if len(words) > 1:
            random.shuffle(words)
            new_content = '、'.join(words)
            return f"{prefix}{new_content}{suffix}"

        return text

    @staticmethod
    def execute_generation(project_name, chapter_name, model, log_func, export_prompt_only=False):
        target_dir = os.path.join(PROJ_DIR, project_name)
        if not os.path.exists(target_dir):
            log_func(f"❌ 错误: 未找到项目目录 {target_dir}")
            return False

        outline_path = os.path.join(target_dir, "chapter_structures", f"{chapter_name}_outline.md")
        chapter_outline = NovelGenerationApp.read_file_safe(outline_path)
        if not chapter_outline:
            log_func(f"❌ 错误: 未找到本章大纲文件 {outline_path}，请先执行 f5a。")
            return False

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
        
        system_prompt = f"""你是一个专业的网络小说作家。你的任务是严格按照【本章执行大纲】进行正文扩写，并完美符合给定的【文风特征】与【词汇偏好】。

【核心约束】：
1. 剧情执行：必须且只能写大纲规定的剧情，严禁自行跳跃大纲或发散额外的世界观设定。
2. 形式模仿：大纲末尾提供的“检索原文参考”仅供学习其遣词造句、句子节奏与环境渲染语调。绝对禁止将原文参考中的具体剧情、人名、功法或事件代入本章正文中。
3. 文本排版：遵循网络小说排版规范，多换行，人物对话独立成段。字数要求在 3000 字左右。
4. 格式输出：直接开始输出小说正文，严禁输出任何形式的解释说明、结构标题或多余的寒暄语。

【底层规则库】：
[文风特征]
{features}

[正向词汇偏好]
{positive_words}

[负向禁用词汇]
{negative_words}
"""

        log_func("正在提取上下文接榫点数据...")
        content_dir = os.path.join(target_dir, "content")
        os.makedirs(content_dir, exist_ok=True)
        previous_context = NovelGenerationApp.get_previous_context(content_dir, chapter_name)

        user_prompt = f"""【前文回顾】（请无缝承接以下段落的物理动作或对话）：
{previous_context}

【本章执行大纲】（含本章必须执行的剧情细节与供模仿的原文参考）：
{chapter_outline}
"""

        # 若是导出模式，直接输出到标准输出供 main.py 捕获，不执行 API
        if export_prompt_only:
            print(f"=== System Prompt ===\n{system_prompt}\n\n=== User Prompt ===\n{user_prompt}")
            return True

        prompt_dir = os.path.join(target_dir, "chapter_specific_prompts")
        os.makedirs(prompt_dir, exist_ok=True)
        prompt_filepath = os.path.join(prompt_dir, f"prompt_{chapter_name}.txt")
        
        try:
            with open(prompt_filepath, 'w', encoding='utf-8') as pf:
                pf.write("=== System Prompt ===\n")
                pf.write(system_prompt + "\n\n")
                pf.write("=== User Prompt ===\n")
                pf.write(user_prompt + "\n")
            log_func(f"已将本章最终指令(含打乱词汇)保存至: {prompt_filepath}")
        except Exception as e:
            log_func(f"保存指令文件失败: {str(e)}")

        log_func("\n>> 提示词构建完毕，正在通过 core 模块连接大模型执行流式生成...\n")
        output_filepath = os.path.join(content_dir, f"{chapter_name}.txt")
        
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                # 调用流式引擎
                for chunk in stream_deepseek_api(system_prompt, user_prompt, model, temperature=0.5):
                    log_func(chunk, append=True)
                    f.write(chunk)
                    f.flush()
            
            # 【关键修改】：去掉了那句伪造 0 Token 的打印，让底层引擎的 Token 打印顺利穿透到界面
            log_func(f"\n\n✅ 章节正文生成完毕！物理文件已落盘至: {output_filepath}")
            return True
        except Exception as e:
            log_func(f"\n❌ 流式生成中断或失败: {str(e)}")
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
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--chapter", type=str, default="")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    parser.add_argument("--branch", type=str, default="", help=argparse.SUPPRESS)
    parser.add_argument("--export_prompt_only", action="store_true", help="仅导出提示词不请求大模型")
    
    args, unknown = parser.parse_known_args()
    
    if not args.project and len(sys.argv) == 1:
        import tkinter as tk
        from tkinter import ttk, messagebox
        root = tk.Tk()
        app = NovelGenerationApp(root)
        root.mainloop()
    else:
        run_headless(args.project, args.chapter, args.model, args.export_prompt_only)