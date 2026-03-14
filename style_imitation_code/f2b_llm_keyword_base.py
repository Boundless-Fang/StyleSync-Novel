import sys
import argparse
import os
import requests
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from dotenv import load_dotenv
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import re

# 加载环境变量以获取 API Key
# 【关键配置】：强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
load_dotenv()

# --- 物理目录严格对齐架构图 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")

class KeywordBaseApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f2b: 大模型词汇清洗与细节分类提取 (RAG 向量检索版)")
        self.root.geometry("600x450")
        self.root.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 8}

        # 1. 原文路径选择
        frame_original = ttk.LabelFrame(self.root, text="1. 选择参考小说原文 (.txt)")
        frame_original.pack(fill="x", **padding)
        self.original_var = tk.StringVar()
        ttk.Entry(frame_original, textvariable=self.original_var, state="readonly", width=55).grid(row=0, column=0, padx=5, pady=10)
        ttk.Button(frame_original, text="浏览...", command=self.select_original).grid(row=0, column=1, padx=5, pady=10)

        # 2. 模型选择
        frame_model = ttk.LabelFrame(self.root, text="2. 选择处理模型")
        frame_model.pack(fill="x", **padding)
        self.model_var = tk.StringVar(value="deepseek-chat")
        ttk.Radiobutton(frame_model, text="DeepSeek V3 (标准)", variable=self.model_var, value="deepseek-chat").pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Radiobutton(frame_model, text="DeepSeek R1 (推理)", variable=self.model_var, value="deepseek-reasoner").pack(side=tk.LEFT, padx=10, pady=5)

        # 3. 执行按钮与日志面板
        self.btn_process = ttk.Button(self.root, text="▶ 执行全量向量化与词汇清洗提取", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=10, width=75, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。将自动读取原文构建向量库，并结合 f2a 提取的高频词进行精准片段检索。")

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
        if not self.original_var.get():
            messagebox.showwarning("提示", "请先选择小说原文文件！")
            return
        self.btn_process.config(state="disabled")
        threading.Thread(target=self.process_logic, daemon=True).start()

    def process_logic(self):
        original_path = self.original_var.get()
        model = self.model_var.get()
        result = self.execute_extraction(original_path, model, self.log, project_name=None)
        if result:
            messagebox.showinfo("完成", "词汇清洗与分类完毕，正面词库已生成。")
        self.btn_process.config(state="normal")

    @staticmethod
    def chunk_text(text, max_len=600):
        """将全量文本按照段落切分为固定长度的文本块"""
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        chunks = []
        current_chunk = ""
        for p in paragraphs:
            if len(current_chunk) + len(p) <= max_len:
                current_chunk += p + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = p + "\n"
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    @staticmethod
    def execute_extraction(original_path, model, log_func, project_name=None):
        try:
            novel_name = os.path.splitext(os.path.basename(original_path))[0]
            words_path = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation", "statistics", "高频词.txt")

            # 1. 读取全量文件与高频词
            try:
                try:
                    with open(original_path, 'r', encoding='utf-8') as f:
                        original_text = f.read() # 读取全量文本用于向量化
                except UnicodeDecodeError:
                    with open(original_path, 'r', encoding='gbk') as f:
                        original_text = f.read()
                    
                words_text = ""
                query_keywords = []
                if os.path.exists(words_path):
                    try:
                        with open(words_path, 'r', encoding='utf-8') as f:
                            words_text = f.read()
                    except UnicodeDecodeError:
                        with open(words_path, 'r', encoding='gbk') as f:
                            words_text = f.read()
                            
                    # 提取高频词列表中括号前的内容作为检索探针
                    matches = re.findall(r'(\S+)\(\d+\)', words_text)
                    query_keywords = matches[:150] # 取前150个高频词作为RAG检索的锚点
                else:
                    log_func("警告：未找到本地高频词文件，无法进行精准 RAG 检索。")
                    return False
            except Exception as e:
                log_func(f"读取文件失败: {e}")
                return False

            # --- 动态目录映射：强制命名为 positive_words.md 对齐架构图 ---
            if project_name:
                target_dir = os.path.join(PROJ_DIR, project_name)
            else:
                target_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
            os.makedirs(target_dir, exist_ok=True)
            save_path = os.path.join(target_dir, "positive_words.md")

            # 2. 文本分块与向量化 (RAG 核心逻辑)
            log_func("正在进行全量文本分块与本地向量化计算...")
            try:
                embedder = SentenceTransformer('shibing624/text2vec-base-chinese')
                chunks = KeywordBaseApp.chunk_text(original_text)
                log_func(f"全文切分为 {len(chunks)} 个文本块。正在生成向量库...")
                
                chunk_embeddings = embedder.encode(chunks, show_progress_bar=False)
                
                dimension = chunk_embeddings.shape[1]
                index = faiss.IndexFlatL2(dimension)
                index.add(np.array(chunk_embeddings).astype('float32'))
                
                # 3. 根据高频词进行检索
                log_func("正在检索与高频词关联的上下文文本块...")
                retrieved_chunks = set()
                
                for i in range(0, len(query_keywords), 15):
                    batch_queries = [" ".join(query_keywords[i:i+15])]
                    query_vec = embedder.encode(batch_queries)
                    distances, indices = index.search(np.array(query_vec).astype('float32'), k=6)
                    for idx in indices[0]:
                        if idx != -1:
                            retrieved_chunks.add(chunks[idx])
                
                context_text = "\n...\n".join(list(retrieved_chunks)[:40])
                log_func(f"成功召回 {len(retrieved_chunks)} 个高相关度片段，即将请求大模型。")
                
            except Exception as e:
                log_func(f"❌ 向量化或检索失败: {str(e)}")
                return False

            log_func("正在请求 API 进行词汇清洗与多维分类...")
            
            # =========================================================================
            # 严格嵌入您的颗粒度细节分类框架作为 Prompt
            # =========================================================================
            prompt_header = """【系统指令】
请仔细阅读提供的参考文本片段以及高频词列表，并严格按照以下结构化的维度框架，提取或者整理对应的关键词与细节描述。
如果每一个项目没有相关词，请标注“无”。
【强制约束】：注意所有词必须来自参考文本本身，不允许造新词。请使用 Markdown 层级输出。

【分类框架】：
一、 容貌
面容：[描述脸型、轮廓、五官比例等基础特征]
眉眼：[描述眉型、眼型、瞳色、睫毛等细节]
口鼻：[描述鼻型、唇形、唇色、牙齿等细节]
皮肤：[描述肤色、肤质、质感、瑕疵或印记等]
发丝：[描述发型、发色、发质、长度、状态等]
二、 气质
内在底色（清/雅/纯/稳/莽）：[描述角色的核心性格底色与内在氛围]
外在展现（冷/贵/柔/英/媚）：[描述角色给人的第一印象与外放气质]
其他气质：[补充不属于上述分类的特殊气质，如病弱、颓废、神秘等]
三、 身材
整体/身高：[描述整体体型（如高挑、娇小、魁梧）及具体身高视觉感]
肩颈/胸臀/腰背：[描述核心躯干的线条、肌肉状态或体态特征]
手臂/腿足：[描述四肢的长度、粗细、力量感或特殊特征]
四、 服饰
种类：[描述穿着的具体服装款式、件数]
材质：[描述布料质地，如丝绸、棉麻、皮革、粗布等]
状态：[描述服装当前的状况，如整洁、破损、褶皱、湿透等]
配饰：[描述佩戴的首饰、挂件、武器等附属物品]
相关动作：[描述与服饰相关的互动，如整理衣领、拉扯袖口、脱下外套等]
五、 对话与表现
逻辑叙事：[描述其表达的主题、说话逻辑或叙事条理性]
状态行为：[描述当前正在进行的整体动作或行为模式]
语气声音：
- 呼吸叫声：[描述呼吸频率、轻重，或特定的叹息、喘息等]
- 语气言语：[描述说话的口吻，如命令、恳求、嘲讽、温柔等]
- 音色音调音量：[描述声音特质，如沙哑、清脆、低沉，及音量大小]
神态表情：
- 表情：[描述面部整体的喜怒哀乐状态]
-气色：[描述面部红润、苍白、铁青等生理性显色]
- 眉眼动作：[描述挑眉、垂眸、眯眼、眼神躲闪等微动作]
- 口鼻动作：[描述咬唇、撇嘴、嗤鼻等微动作]
情绪心理：
- 心理活动：[描述其内心的真实想法或潜台词]
- 正面情绪：[描述喜悦、期待、安心等积极情绪表现]
- 负面情绪：[描述愤怒、恐惧、悲伤等消极情绪表现]
肢体语言：
- 头颈发丝：[描述点头、歪头、撩拨头发等动作]
- 手臂指尖：[描述手势、握拳、指尖颤抖等动作]
- 躯干核心：[描述挺胸、佝偻、后退、僵硬等躯干动作]
- 腿足脚趾：[描述步伐、抖腿、脚趾蜷缩等下肢动作]
生理细节：
- 体液气味：[描述汗水、泪水、血液，及身上的香气或体味]
- 皮肤肌肉：[描述鸡皮疙瘩、肌肉紧绷、青筋暴起等细节]
- 内脏/神经/呼吸：[描述心跳加速、胃部痉挛、耳鸣等深层生理反应]
- 其他：[其他未分类的生理特征]
五感表现：
- 温度：[描述冷、热、温热、冰凉等感知]
- 触感：[描述粗糙、柔软、刺痛、摩擦等体验]
- 光影：[描述视觉上的明暗变化、色彩对比等]
六、 交互
空间距离：[描述角色间的物理距离及变化，如逼近、退后、并肩]
视线交互：[描述目光的交汇、躲闪、凝视或压迫性注视]
气场碰撞：[描述双方气质和情绪交锋时的氛围感或张力]
七、 环境与氛围
场景：[描述所处的具体物理空间、时间、天气或布景]
氛围：[描述场景整体烘托出的情感基调，如压抑、温馨、肃杀等]

【高频词列表】：
"""
            prompt = prompt_header + words_text + "\n\n【经 RAG 检索提取的高相关度参考文本片段】：\n" + context_text

            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                log_func("error: 未能在环境变量中找到 DEEPSEEK_API_KEY")
                return False

            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个严谨的词汇分析与提取引擎。请严格按照要求输出 Markdown 格式的纯文本列表。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2 # 极低温度，保证客观提取，杜绝幻觉和造词
            }
            
            response = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            result_text = response.json()['choices'][0]['message']['content'].strip()
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(result_text)
            
            log_func(f"✅ 提取与分类完成！词库文件已落盘至: {save_path}")
            return True
        except Exception as e:
            log_func(f"❌ 分析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(target_file, project_name=None, model="deepseek-chat"):
    """供后端 API 调用的后台静默执行入口"""
    if os.path.isabs(target_file):
        original_path = target_file
    else:
        original_path = os.path.join(REFERENCE_DIR, target_file)
        
    if not os.path.exists(original_path):
        print(f"error: 未找到参考小说原文 {original_path}")
        sys.exit(1)
    
    print(f"开始静默执行词库清洗与多维提取: {original_path}")
    success = KeywordBaseApp.execute_extraction(original_path, model, print, project_name)
    if success:
        print("词库清洗任务成功完成。")
    else:
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="大模型词汇清洗分类")
    parser.add_argument("--target_file", type=str, help="参考小说原文的绝对路径或文件名", default="")
    parser.add_argument("--project", type=str, help="绑定的项目名称", default="")
    parser.add_argument("--model", type=str, help="使用的模型名称", default="deepseek-chat")
    
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        root = tk.Tk()
        app = KeywordBaseApp(root)
        root.mainloop()
    else:
        if not args.target_file and unknown and not unknown[0].startswith('--'):
            args.target_file = unknown[0]
            
        run_headless(args.target_file, args.project, args.model)