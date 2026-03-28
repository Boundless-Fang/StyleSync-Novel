# --- File: f3c_llm_character.py ---
import os
import re
import json
import math
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
# 2. 导入 core 模块
# =====================================================================
from core._core_config import BASE_DIR, PROJECT_ROOT, REFERENCE_DIR, STYLE_DIR, PROJ_DIR
from core._core_utils import smart_read_text
from core._core_llm import call_deepseek_api
from core._core_rag import RAGRetriever

class CharacterProfileApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f3c: 角色信息卡提取 (对数动态限量 + 批量处理版)")
        self.root.geometry("680x580")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        # --- 区域 1：原文选择 ---
        frame_original = ttk.LabelFrame(self.root, text="1. 选择小说原文 (.txt)")
        frame_original.pack(fill="x", **padding)
        self.original_var = tk.StringVar()
        ttk.Entry(frame_original, textvariable=self.original_var, state="readonly", width=60).grid(row=0, column=0, padx=5, pady=10)
        ttk.Button(frame_original, text="浏览...", command=self.select_original).grid(row=0, column=1, padx=5, pady=10)

        # --- 区域 2：批量角色解析与输入 ---
        frame_char = ttk.LabelFrame(self.root, text="2. 目标角色名单 (支持自动解析与手动补充)")
        frame_char.pack(fill="x", **padding)
        
        btn_frame = ttk.Frame(frame_char)
        btn_frame.pack(fill="x", padx=5, pady=2)
        ttk.Button(btn_frame, text="⚡ 从世界观(f3b)自动智能解析角色", command=self.auto_load_characters).pack(side=tk.LEFT)
        ttk.Label(btn_frame, text="* 自动依据对数模型计算提取上限，其余可手动输入", foreground="gray").pack(side=tk.LEFT, padx=10)

        self.char_text = tk.Text(frame_char, height=6, width=80)
        self.char_text.pack(padx=5, pady=5)
        self.char_text.insert(tk.END, "请点击上方按钮自动解析，或在此处手动输入角色名（每行一个）。\n格式例：\n林动\n林动(武祖、林动哥)")

        # --- 区域 3：模型选择 ---
        frame_model = ttk.LabelFrame(self.root, text="3. 选择处理模型")
        frame_model.pack(fill="x", **padding)
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Radiobutton(frame_model, text="DeepSeek V3 (标准)", variable=self.model_var, value="deepseek-chat").pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Radiobutton(frame_model, text="DeepSeek R1 (推理)", variable=self.model_var, value="deepseek-reasoner").pack(side=tk.LEFT, padx=10, pady=5)
        
        # --- 执行按钮与日志 ---
        self.btn_process = ttk.Button(self.root, text="▶ 执行全量向量检索与批量角色卡提取", command=self.start_process_thread)
        self.btn_process.pack(pady=5)

        self.log_text = tk.Text(self.root, height=10, width=85, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。支持基于字数的动态对数限制机制。")

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def select_original(self):
        init_dir = REFERENCE_DIR if os.path.exists(REFERENCE_DIR) else BASE_DIR
        path = filedialog.askopenfilename(initialdir=init_dir, title="选择原文", filetypes=[("Text Files", "*.txt")])
        if path: self.original_var.set(path)

    def auto_load_characters(self):
        original_path = self.original_var.get()
        if not original_path or not os.path.exists(original_path):
            import tkinter.messagebox as messagebox
            messagebox.showwarning("提示", "请先选择有效的参考原文！")
            return

        novel_name = os.path.splitext(os.path.basename(original_path))[0]
        settings_path = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "world_settings.md")

        if not os.path.exists(settings_path):
            import tkinter.messagebox as messagebox
            messagebox.showwarning("提示", "未找到世界观设定(world_settings.md)，请确保已执行 f3b 环节！")
            return

        self.log("正在计算文本体量并解析 f3b 角色列表...")
        
        # 1. 动态对数计算容量上限 N
        try:
            text_content = smart_read_text(original_path)
            text_len = len(text_content)
            # 核心算法: N = 5 * log10(L / 10000)，保底 3 个
            if text_len < 10000:
                limit = 3
            else:
                limit = max(3, int(5 * math.log10(text_len / 10000.0)))
        except Exception as e:
            self.log(f"⚠️ 原文长度计算失败，默认限制提取 5 个角色。({str(e)})")
            text_len = "未知"
            limit = 5

        # 2. 从设定中正则提取角色
        try:
            settings_text = smart_read_text(settings_path)
            # 匹配 "出场角色以及别名：..." 后面的内容
            match = re.search(r'出场角色.*?[：:]\s*(.*)', settings_text)
            if not match:
                self.log("❌ 无法在 world_settings.md 中定位到 [出场角色] 字段，请检查设定文件格式。")
                return

            chars_str = match.group(1).strip()
            
            # 使用进阶正则分割：按顿号/逗号分割，但忽略括号内的逗号
            raw_chars = re.findall(r'[^、，,（(]+(?:\([^)]+\)|（[^）]+）)?', chars_str)
            raw_chars = [c.strip() for c in raw_chars if c.strip() and len(c.strip()) > 1]

            if not raw_chars:
                self.log("❌ 提取到的角色列表为空。")
                return

            # 3. 执行截断并应用到界面
            selected_chars = raw_chars[:limit]
            self.log(f"📊 原文体量: ~{text_len} 字。基于对数模型 (N=5*log10(L/1w))，建议提取上限为 {limit} 个。")
            self.log(f"✅ 成功从原著世界观中提取出 {len(selected_chars)} 个主要角色！")

            self.char_text.delete("1.0", tk.END)
            self.char_text.insert(tk.END, "\n".join(selected_chars))
            
        except Exception as e:
            self.log(f"❌ 自动解析发生错误: {str(e)}")


    def start_process_thread(self):
        import tkinter.messagebox as messagebox
        if not self.original_var.get():
            messagebox.showwarning("提示", "请选择原文文件！")
            return
            
        chars_input = self.char_text.get("1.0", tk.END).strip()
        if not chars_input or "请点击上方按钮自动解析" in chars_input:
            messagebox.showwarning("提示", "角色名单不能为空，请自动提取或手动输入！")
            return
            
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, daemon=True).start()

    def process_logic(self):
        import tkinter.messagebox as messagebox
        original_path = self.original_var.get()
        model = self.model_var.get()
        
        # 将文本框内容切分为列表
        chars_list = self.char_text.get("1.0", tk.END).strip().split('\n')
        chars = [c.strip() for c in chars_list if c.strip()]
        
        success_count = 0
        total_count = len(chars)

        self.log(f"\n🚀 开始执行批量角色卡提取任务，共计 {total_count} 个目标角色。")
        
        for idx, char_name in enumerate(chars, 1):
            self.log(f"\n--- [任务 {idx}/{total_count}] 正在追踪提取: {char_name} ---")
            result = self.execute_extraction(original_path, char_name, model, self.log, project_name=None)
            if result:
                success_count += 1

        self.log(f"\n🎉 批量任务结束！成功提取 {success_count}/{total_count} 个角色。")
        messagebox.showinfo("完成", f"批量角色卡提取完毕！成功 {success_count}/{total_count} 个。")
        self.btn_process.config(state="normal")

    @staticmethod
    def parse_character_names(char_input):
        char_input = char_input.replace('（', '(').replace('）', ')')
        if '(' in char_input and char_input.endswith(')'):
            main_name = char_input.split('(')[0].strip()
            aliases_str = char_input.split('(')[1][:-1]
            aliases = [a.strip() for a in re.split(r'[,，、]', aliases_str) if a.strip()]
            return main_name, [main_name] + aliases
        return char_input.strip(), [char_input.strip()]

    @staticmethod
    def execute_extraction(original_path, character_input, model, log_func, project_name=None):
        try:
            novel_name = os.path.splitext(os.path.basename(original_path))[0]
            main_name, search_keywords = CharacterProfileApp.parse_character_names(character_input)
            
            style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
            rag_db_dir = os.path.join(style_dir, "global_rag_db")
            index_path = os.path.join(rag_db_dir, "vector.index")
            chunks_path = os.path.join(rag_db_dir, "chunks.json")

            if not os.path.exists(index_path) or not os.path.exists(chunks_path):
                 log_func("❌ 致命错误：未找到全局 RAG 索引。请先执行 f0 初始化！")
                 return False

            style_char_dir = os.path.join(style_dir, "character_profiles")
            os.makedirs(style_char_dir, exist_ok=True)
            save_path = os.path.join(style_char_dir, f"{main_name}.md")
            
            project_save_path = None
            if project_name:
                project_dir = os.path.join(PROJ_DIR, project_name, "character_profiles")
                os.makedirs(project_dir, exist_ok=True)
                project_save_path = os.path.join(project_dir, f"{main_name}.md")

            log_func(f"正在加载全局 RAG 索引并定向追踪角色: {search_keywords}")
            try:
                retriever = RAGRetriever()
                index, chunks = retriever.load_index(index_path, chunks_path)
                
                meta_queries = [
                    f"{main_name} 外貌 气质 衣服 长相",
                    f"{main_name} 境界 功法 武器 战斗",
                    f"{main_name} 父母 身世 过去 经历",
                    f"{main_name} 性格 说话 笑道 怒道"
                ]
                all_queries = search_keywords + meta_queries
                
                retrieved_chunks = retriever.search(index, chunks, all_queries, k=8, batch_size=3)
                context_text = "\n...\n".join(retrieved_chunks[:50]) 
                log_func(f"成功召回 {min(len(retrieved_chunks), 50)} 个包含该角色的高相关度片段。")
                
            except Exception as e:
                log_func(f"❌ 向量化或检索失败: {str(e)}")
                return False

            log_func("正在调用大模型生成角色卡片...")
            prompt_header = f"""【系统指令】：
请基于提供的“文本高相关度片段”，为角色【{character_input}】提取并总结信息卡片。
必须严格遵循原文，如果某项在文本中确实没有提及，请填“未知”。必须使用 Markdown 结构输出。

【固定输出板块与格式】：
### 一、 基础属性
- **名字**：
- **人物类型**：（在 男主角、女主角、配角、反派 中选择）
- **人物塑造**：（在 圆形人物/扁平人物 中选择）
- **相关关键词**：（3-5个核心词）

### 二、 相关信息
- **身份**：（社会身份/职业，以及人际关系如“XX的徒弟/XX的妻子”）
- **性格**：
- **外貌/气质/身材/服饰**：
- **主要能力特点/境界**：
- **年龄与主要经历**：

### 三、 价值观
从以下列表中严格选出五个在该角色心中最重要的价值观，并用 `>` 进行排序（例如：复活爱人 > 宗门传承 > 尊严 > 力量 > 生命）：
列表：执念/理想（大道/长生/天下/自由/复活爱人等）、集体（种族/国家/宗门等）/传承、道心/原则/尊严、爱情/爱人、子嗣/父母/师傅/亲人/好友等、恩情/承诺、贞洁/性、自我/生命、力量/资源/金钱/权力等。
- **核心价值观排序**：
- **人物弱点**：
- **相关高频词**：

### 四、 对主要角色的态度
（提取与该角色有互动的其他主要角色，说明对其称呼及好感度。好感度从低到高限选：仇恨、厌恶、冷漠、陌生、好感、亲近、深情）
- **对[角色A]**：称呼为...，态度为[填入好感度]，补充说明...
- **对[角色B]**：...

### 五、 语言习惯与音色
- **语言习惯与音色**：

【文本高相关度片段 (经 RAG 检索提取)】：
"""
            prompt = prompt_header + context_text
            sys_prompt = "你是一个严谨的小说设定整理专家。严格遵守原著，空缺项目填未知，只输出 Markdown。"

            try:
                result_text = call_deepseek_api(system_prompt=sys_prompt, user_prompt=prompt, model=model, temperature=0.2)
                
                # 基础防呆校验
                if "一、 基础属性" not in result_text and "基础属性" not in result_text:
                    log_func(f"⚠️ 警告：[{main_name}] 返回的内容可能缺失了 Markdown 骨架结构，建议人工检查。")

                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(result_text)
                    
                msg = f"✅ [{main_name}] 构建完成！落盘至: {save_path}"
                if project_save_path:
                    import shutil
                    shutil.copy2(save_path, project_save_path)
                    
                log_func(msg)
                return True
            except Exception as e:
                log_func(f"❌ API 调用失败: {str(e)}")
                return False
        except Exception as e:
            log_func(f"❌ 分析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(target_file, character_list_str, project_name=None, model="deepseek-chat"):
    import sys
    if os.path.isabs(target_file):
        original_path = target_file
    else:
        original_path = os.path.join(REFERENCE_DIR, target_file)
        
    if not os.path.exists(original_path):
        print(f"error: 未找到原文 {original_path}")
        sys.exit(1)
    
    chars = [c.strip() for c in character_list_str.split(',') if c.strip()]
    if not chars:
        print("error: 角色列表为空")
        sys.exit(1)
        
    print(f"开始静默执行 RAG 角色卡批量提取，共 {len(chars)} 个目标...")
    for char_name in chars:
        print(f"-> 提取角色: {char_name}")
        CharacterProfileApp.execute_extraction(original_path, char_name, model, print, project_name)

if __name__ == "__main__":
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, default="")
    parser.add_argument("--character", type=str, default="", help="静默模式下使用逗号分隔传入多个角色名") 
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        # P0修复：在此处下沉延迟加载 tkinter
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        app = CharacterProfileApp(root)
        root.mainloop()
    else:
        if not args.character:
            print("error: 静默模式必须提供 --character 参数 (多个角色用逗号隔开)")
            sys.exit(1)
        run_headless(args.target_file, args.character, args.project, args.model)