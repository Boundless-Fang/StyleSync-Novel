import sys
import argparse
import os

# 【关键配置】：强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import requests
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import threading
from dotenv import load_dotenv
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import re

load_dotenv()

# --- 物理目录对齐 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")

class CharacterProfileApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f3c: 角色信息卡提取 (RAG 定向追踪版)")
        self.root.geometry("650x500")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        frame_original = ttk.LabelFrame(self.root, text="1. 选择小说原文 (.txt)")
        frame_original.pack(fill="x", **padding)
        self.original_var = tk.StringVar()
        ttk.Entry(frame_original, textvariable=self.original_var, state="readonly", width=60).grid(row=0, column=0, padx=5, pady=10)
        ttk.Button(frame_original, text="浏览...", command=self.select_original).grid(row=0, column=1, padx=5, pady=10)

        frame_char = ttk.LabelFrame(self.root, text="2. 指定目标角色")
        frame_char.pack(fill="x", **padding)
        self.character_var = tk.StringVar()
        ttk.Entry(frame_char, textvariable=self.character_var, width=60).grid(row=0, column=0, padx=5, pady=10)
        ttk.Label(frame_char, text="(格式例：林动 或 林动(武祖、林动哥))", foreground="gray").grid(row=1, column=0, sticky="w", padx=5)

        frame_model = ttk.LabelFrame(self.root, text="3. 选择处理模型")
        frame_model.pack(fill="x", **padding)
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Radiobutton(frame_model, text="DeepSeek V3 (标准)", variable=self.model_var, value="deepseek-chat").pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Radiobutton(frame_model, text="DeepSeek R1 (推理)", variable=self.model_var, value="deepseek-reasoner").pack(side=tk.LEFT, padx=10, pady=5)
        
        self.btn_process = ttk.Button(self.root, text="▶ 全文定向检索与提取角色卡", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=8, width=80, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。")

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

    def start_process_thread(self):
        if not self.original_var.get() or not self.character_var.get().strip():
            messagebox.showwarning("提示", "请选择原文文件并输入目标角色名！")
            return
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, daemon=True).start()

    def process_logic(self):
        original_path = self.original_var.get()
        model = self.model_var.get()
        character_input = self.character_var.get().strip()
        result = self.execute_extraction(original_path, character_input, model, self.log, project_name=None)
        if result:
            messagebox.showinfo("完成", f"[{character_input}] 角色卡构建完毕！")
        self.btn_process.config(state="normal")

    @staticmethod
    def chunk_text(text, max_len=600):
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        chunks, current_chunk = [], ""
        for p in paragraphs:
            if len(current_chunk) + len(p) <= max_len:
                current_chunk += p + "\n"
            else:
                if current_chunk: chunks.append(current_chunk.strip())
                current_chunk = p + "\n"
        if current_chunk: chunks.append(current_chunk.strip())
        return chunks

    @staticmethod
    def parse_character_names(char_input):
        """解析如 '张小凡(鬼厉, 小凡)' 的字符串，提取主名和别名"""
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
            
            # 确定读取与落盘的物理路径
            if project_name:
                target_dir = os.path.join(PROJ_DIR, project_name, "character_profiles")
            else:
                target_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "character_profiles")
            os.makedirs(target_dir, exist_ok=True)
            
            # 角色卡文件命名
            save_path = os.path.join(target_dir, f"{main_name}.md")

            try:
                try:
                    with open(original_path, 'r', encoding='utf-8') as f:
                        full_text = f.read()
                except UnicodeDecodeError:
                    with open(original_path, 'r', encoding='gbk') as f:
                        full_text = f.read()
            except Exception as e:
                log_func(f"读取文件失败: {e}")
                return False

            # 2. 文本分块与向量化 (定向 RAG 核心逻辑)
            log_func(f"正在全量向量化，并定向追踪角色: {search_keywords}")
            try:
                embedder = SentenceTransformer('shibing624/text2vec-base-chinese')
                chunks = CharacterProfileApp.chunk_text(full_text)
                chunk_embeddings = embedder.encode(chunks, show_progress_bar=False)
                
                dimension = chunk_embeddings.shape[1]
                index = faiss.IndexFlatL2(dimension)
                index.add(np.array(chunk_embeddings).astype('float32'))
                
                retrieved_chunks = set()
                
                # 强化检索维度：除了名字，加上外貌、战斗、身世等诱导词强行抓取特征
                meta_queries = [
                    f"{main_name} 外貌 气质 衣服 长相",
                    f"{main_name} 境界 功法 武器 战斗",
                    f"{main_name} 父母 身世 过去 经历",
                    f"{main_name} 性格 说话 笑道 怒道"
                ]
                all_queries = search_keywords + meta_queries
                
                for i in range(0, len(all_queries), 3):
                    batch_queries = [" ".join(all_queries[i:i+3])]
                    query_vec = embedder.encode(batch_queries)
                    distances, indices = index.search(np.array(query_vec).astype('float32'), k=8) 
                    for idx in indices[0]:
                        if idx != -1:
                            retrieved_chunks.add(chunks[idx])
                
                context_text = "\n...\n".join(list(retrieved_chunks)[:50]) # 给定足够的上下文碎片
                log_func(f"成功召回 {len(retrieved_chunks)} 个包含该角色的高相关度片段。")
                
            except Exception as e:
                log_func(f"❌ 向量化或检索失败: {str(e)}")
                return False

            # 4. 请求大语言模型构建角色卡
            log_func("正在调用大模型重组角色信息卡...")
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

            api_key = os.getenv("DEEPSEEK_API_KEY")
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个严谨的小说设定整理专家。严格遵守原著，空缺项目填未知，只输出 Markdown。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2
            }
            
            try:
                response = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=180)
                response.raise_for_status()
                result_text = response.json()['choices'][0]['message']['content'].strip()
                
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(result_text)
                log_func(f"✅ 角色卡构建完成！文件落盘至: {save_path}")
                return True
            except Exception as e:
                log_func(f"❌ API 调用失败: {str(e)}")
                return False
        except Exception as e:
            log_func(f"❌ 分析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(target_file, character_name, project_name=None, model="deepseek-chat"):
    if os.path.isabs(target_file):
        original_path = target_file
    else:
        original_path = os.path.join(REFERENCE_DIR, target_file)
        
    if not os.path.exists(original_path):
        print(f"error: 未找到原文 {original_path}")
        sys.exit(1)
    
    print(f"开始静默执行 RAG 角色卡提取: {character_name}")
    success = CharacterProfileApp.execute_extraction(original_path, character_name, model, print, project_name)
    if not success: sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_file", type=str, default="")
    parser.add_argument("--character", type=str, default="") # 新增的角色参数
    parser.add_argument("--project", type=str, default="")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        root = tk.Tk()
        app = CharacterProfileApp(root)
        root.mainloop()
    else:
        # 如果是静默调用但缺少角色参数，安全退出
        if not args.character:
            print("error: 必须提供 --character 参数")
            sys.exit(1)
        run_headless(args.target_file, args.character, args.project, args.model)