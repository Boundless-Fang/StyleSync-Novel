import os
import sys
import argparse
import requests
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from dotenv import load_dotenv

# 加载环境变量以获取 API Key
load_dotenv()

# --- 物理目录严格对齐架构图 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")

class StyleAnalysisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("f1b: 文风与行文特征深度提取 (大模型版)")
        self.root.geometry("600x400")
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
        self.btn_process = ttk.Button(self.root, text="▶ 开始提取文风特征", command=self.start_process_thread)
        self.btn_process.pack(pady=10)

        self.log_text = tk.Text(self.root, height=8, width=75, state="disabled", bg="#f8f9fa")
        self.log_text.pack(padx=10, pady=5)
        self.log("系统就绪。请选择原文并执行。")

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
        result = self.execute_analysis(original_path, model, self.log, project_name=None)
        if result:
            messagebox.showinfo("完成", f"文风特征提取完毕，文件已生成。")
        self.btn_process.config(state="normal")

    @staticmethod
    def execute_analysis(original_path, model, log_func, project_name=None):
        novel_name = os.path.splitext(os.path.basename(original_path))[0]
        try:
            try:
                with open(original_path, 'r', encoding='utf-8') as f:
                    original_text = f.read(50000)
            except UnicodeDecodeError:
                with open(original_path, 'r', encoding='gbk') as f:
                    original_text = f.read(50000)
        except Exception as e:
            log_func(f"读取文件失败: {e}")
            return False

        try:
            # --- 动态目录映射，严格统一文件名为 features.md ---
            if project_name:
                target_dir = os.path.join(PROJ_DIR, project_name)
                os.makedirs(target_dir, exist_ok=True)
                save_path = os.path.join(target_dir, "features.md")
            else:
                target_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
                os.makedirs(target_dir, exist_ok=True)
                save_path = os.path.join(target_dir, "features.md")

            log_func("正在请求 API 进行文风特征动态分析...")
            
            # =========================================================================
            # 提示词部分一：发送给 AI 进行动态特征提取
            # =========================================================================
            prompt_header = """使用严谨客观的语言，按照以下格式总结该小说的行文特点，不要包含具体的剧情内容和人物名字，允许分类讨论，比如...：在...时...；在...时...。在有标注“举例”的项目里要附上若干示例。
一、行文风格
叙事节奏：推进故事发展或展现事件细节的速度等分类：快节奏（动作冲突密集）/慢节奏（侧重心理与环境铺垫）/快慢交替/延宕（在关键节点故意放缓拉扯）等
语体色彩：文本遣词造句呈现出的整体质感与语言属性等分类：书面典雅（文艺/古风）/通俗易懂/文白混杂等
叙事语调：叙述者对待故事、角色或读者所持的情感态度与说话腔调等分类：冷静理智/幽默吐槽/热血中二等
描写风格：呈现事物状态时的笔墨浓淡与画面质感等分类：白描（寥寥数笔极简勾勒）/工笔（繁复细腻纤毫毕现）等
二、格式要求
人称视角：叙述者观察和讲述故事的立足点等分类：第一人称（主观代入）/第三人称全知视角（上帝视角）/第三人称限制视角（单人跟随视角）等
句段长度：文本在视觉排版与阅读呼吸停顿上的物理切分等分类：长句为主/短句为主/长短句交替 + 长段为主/短段为主/长短段交替等
心理呈现：向读者揭示角色内在思想与情绪波动的途径等分类：内心独白（逻辑清晰的自我剖析）/意识流（无序跳跃的脑内碎片）/动作神态暗示（冰山理论，不直接点破）/全知旁白揭示等（举例）
对话处理：角色言语交流在文本中的展现形态等分类：直接引语（带“他说”等提示语）/剥离提示语（纯对话交锋）/间接引语（揉入旁白转述）/舞台剧式长篇独白/日常碎片式短句等（举例）
标点习惯：作者在标点符号使用上的特殊偏好，直接影响文字韵律等分类：常规规范/少逗号（一气呵成的流线感）/多逗号（促音与压迫感）/破折号偏好（思维跳跃/转折）/省略号偏好（留白余韵）等，包括场景切换时的标点习惯
三、手法偏好
表达方式：文本承载信息、推进内容的最基础逻辑功能等分类：记叙（交代经过）/描写（刻画状态）/抒情（表达情感）/议论（发表观点）/说明（客观介绍）等
表现手法：为深化主旨或强化艺术感染力而采用的中宏观构思技巧等分类：象征/对比/烘托（正衬/反衬）/虚实结合/欲扬先抑（欲抑先扬）/托物言志等（举例）
描写角度：观察感知并呈现描写对象的切入点与感官维度等分类：正面描写（直接刻画）/侧面描写（通过他物他人反应烘托） + 视觉/听觉/嗅觉/味觉/触觉/通感等（举例）
修辞手法：作用于字句微观层面，增强语言生动性的技巧等分类：比喻（明/暗/借喻）/拟人（拟物）/夸张/排比/设问/反问/借代/双关等（举例）
四、具体内容（习惯从哪些角度/方面描写哪些内容，此处举例必须引用原文）
外貌偏好：气质、容貌、服饰、身材、发色、发型、身体特征、光影等（举例）
动作偏好：神态、肢体、下意识、细节等（举例）
对话/心理偏好：网络用语、粗俗用语、特殊称呼、语气词、拟声词等（举例）

【参考原文片段】（前50000字截取）：
"""
            prompt_part_1 = prompt_header + original_text

            # =========================================================================
            # 提示词部分二：静态禁止事项约束（在 AI 返回后拼接）
            # =========================================================================
            prompt_part_2 = """五、禁止事项
1.比较定义（是否出现以下句式）：
“与其说……不如说……”
“（仿佛）不是A，而是B”
“那不是A，也不是B，而是一种C”
“这（它）是一种A，也是一种B”
“这（像）是一场/次/个+[抽象概念]（如：献祭，掠夺，占有，仪式，洗礼等）”
“带着一种……”
2.解释说明：
禁止解释动作背后的原因（如：“因为醉酒而……”，“为了发泄而……”，“出于本能……”）。
只写动作本身，不写为什么做这个动作。
3.抽象描写：
禁止使用无法被视网膜捕捉或触觉神经感知的抽象词汇，比如疯狂的、剧烈的、猛烈的、极致的、极度的、巨大的、彻底的、残忍的、疯狂的、不容置疑的、爆炸性的、绝望的、无助的、难以言喻的、无法形容的、不可思议的、孤注一掷的、带有侵略性的、带有惩罚性的、令人窒息的、下意识的、本能的、狂风骤雨般
禁止出现“理智的弦（断了/崩塌）”。
禁止出现“大脑一片空白”、“思维停滞”。
禁止出现“心底升起……”，“灵魂深处……”
禁止“……猛地/轰然炸开”。
禁止“……被劈成了两半”。
禁止“灭顶的快感”、“毁灭性的（冲刺/力量）”。
禁止“灵魂深处……”，“直达灵魂”。
禁止“充满了……的（气息/味道/感觉）”
4.陈词滥调：
绝对禁止：带着哭腔、仿佛能滴出水来、带着不容置疑的语气
5.错误比喻：
绝对禁止：破布娃娃（及人偶、偶人、木偶、断了线的木偶、布娃娃、娃娃等）、濒死的/被抛上岸/砧板上鱼、像一盆冰水、像一把重锤、淬了毒的...、飓风、被抽去骨头的...、祭品、待宰的...、牲畜、最锋利的冰锥、离了水的鱼、重型卡车、灵魂出窍、空白/空白的大脑、行驶的列车/火车、虔诚的...、撞击、山崩地裂、火山爆发、龙卷风、洪流、子弹、炮弹、燎原的火、掠夺、信徒、攻城锤、岩浆、海藻、破碎（形容声音或身体）。
尽量避免：火星、洪流、毒蛇、小船、催化剂、催情药、小兽、烟花、爆炸、船桨、划船、攻城略地、开疆拓土、机器/机械的、溺水、容器、每一个毛孔都在叫嚣、五脏六腑都错了位、毒刺、羽毛、拉风箱。"""

            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                log_func("error: 未能在环境变量中找到 DEEPSEEK_API_KEY")
                return False

            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个严谨的文本分析程序。请严格按照要求输出 Markdown 格式的纯文本，不要包含任何多余的寒暄。"},
                    {"role": "user", "content": prompt_part_1}
                ],
                "temperature": 0.3 # 降低随机性
            }
            
            response = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            
            # 获取 AI 生成的“部分一”结果
            analysis_result = response.json()['choices'][0]['message']['content'].strip()
            
            # 将生成的“部分一”与静态的“部分二”进行物理拼接
            final_output = f"{analysis_result}\n\n{prompt_part_2}"
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(final_output)
            
            log_func(f"✅ 分析与拼接完成！最终设定文件已落盘至: {save_path}")
            return True

        except Exception as e:
            log_func(f"❌ 分析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def run_headless(target_file, project_name=None, model="deepseek-chat"):
    """供后端 API 调用的后台静默执行入口"""
    def safe_log(msg):
        try:
            print(msg)
        except UnicodeEncodeError:
            try:
                sys.stdout.buffer.write((msg + "\n").encode('utf-8'))
            except Exception:
                print(msg.encode('gbk', 'replace').decode('gbk'))

    if os.path.isabs(target_file):
        original_path = target_file
    else:
        original_path = os.path.join(REFERENCE_DIR, target_file)
        
    if not os.path.exists(original_path):
        safe_log(f"error: 未找到参考小说原文 {original_path}")
        sys.exit(1)
    
    safe_log(f"开始静默分析文风特征: {original_path}")
    success = StyleAnalysisApp.execute_analysis(original_path, model, safe_log, project_name)
    if success:
        safe_log("文风分析与规则拼接任务成功完成。")
    else:
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="大模型深层文风特征提取")
    parser.add_argument("--target_file", type=str, help="参考小说原文的绝对路径或文件名", default="")
    parser.add_argument("--project", type=str, help="绑定的项目名称", default="")
    parser.add_argument("--model", type=str, help="使用的模型名称", default="deepseek-chat")
    
    args, unknown = parser.parse_known_args()
    
    if not args.target_file and len(sys.argv) == 1:
        root = tk.Tk()
        app = StyleAnalysisApp(root)
        root.mainloop()
    else:
        if not args.target_file and unknown and not unknown[0].startswith('--'):
            args.target_file = unknown[0]
            
        run_headless(args.target_file, args.project, args.model)