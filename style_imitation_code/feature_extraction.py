import os
import json
import requests
import tkinter as tk
from tkinter import filedialog, messagebox
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 基础路径配置
BASE_DIR = r"D:\StyleSync-Novel"
STATISTICS_DIR = os.path.join(BASE_DIR, "text_statistics")
FEATURES_DIR = os.path.join(BASE_DIR, "text_features")
REFERENCE_DIR = os.path.join(BASE_DIR, "reference_novels")

def extract_features_api(text_content, original_text, model_choice):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("未读取到 API 密钥。请检查 .env 文件。")
        return None

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # 构建包含原文和统计文本的上下文
    combined_input = f"【参考原文片段】\n{original_text}\n\n【统计文本片段】\n{text_content}"
    
    payload = {
        "model": model_choice,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个严谨的文本信息提取程序。请结合提供的【参考原文片段】和【统计文本片段】，"
                    "提取文本中的专有词和高频关键名词，并进行分类。必须严格输出为JSON格式，"
                    "包含以下键（对应值为字符串列表）："
                    "'person_names'（人名）、'place_names'（地名）、'factions'（势力/单位）、"
                    "'power_systems'（力量体系）、'internet_slang'（网络词）、'keywords'（其他高频关键词）。"
                    "请勿输出JSON以外的任何解释性文字。"
                )
            },
            {
                "role": "user",
                "content": combined_input
            }
        ],
        "response_format": {"type": "json_object"}
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return json.loads(result['choices'][0]['message']['content'])
    except Exception as e:
        print(f"API 请求失败: {e}")
        return None

def select_folder():
    if not os.path.exists(STATISTICS_DIR):
        os.makedirs(STATISTICS_DIR)
    folder_path = filedialog.askdirectory(title="选择小说统计文件夹", initialdir=STATISTICS_DIR)
    if folder_path:
        folder_path_var.set(folder_path)
        folder_name = os.path.basename(folder_path)
        novel_name = folder_name.replace("_统计", "") if folder_name.endswith("_统计") else folder_name
        novel_name_var.set(novel_name)

def select_original_file():
    if not os.path.exists(REFERENCE_DIR):
        os.makedirs(REFERENCE_DIR)
    file_path = filedialog.askopenfilename(title="选择小说原文文件", initialdir=REFERENCE_DIR, filetypes=[("Text Files", "*.txt")])
    if file_path:
        original_file_var.set(file_path)

def start_process():
    folder_path = folder_path_var.get()
    novel_name = novel_name_var.get().strip()
    original_file_path = original_file_var.get()
    model_choice = model_var.get()

    if not folder_path or not original_file_path:
        messagebox.showwarning("提示", "请确保已选择统计文件夹和小说原文文件。")
        return

    # 读取统计文件夹内容
    combined_stats_text = ""
    try:
        for file_name in os.listdir(folder_path):
            if file_name.endswith(".txt"):
                with open(os.path.join(folder_path, file_name), 'r', encoding='utf-8') as f:
                    combined_stats_text += f.read() + "\n"
    except Exception as e:
        messagebox.showerror("错误", f"读取统计文件夹失败：\n{e}")
        return

    # 读取原文内容
    original_text = ""
    try:
        with open(original_file_path, 'r', encoding='utf-8') as f:
            original_text = f.read(5000) # 读取前5000字符作为上下文比对
    except Exception as e:
        messagebox.showerror("错误", f"读取小说原文失败：\n{e}")
        return

    if not combined_stats_text.strip():
        messagebox.showwarning("提示", "统计文件夹内无文本内容。")
        return

    text_to_process = combined_stats_text[:3000]
    btn_process.config(state=tk.DISABLED)
    status_var.set(f"状态：正在调用 {model_choice} API，请稍候...")
    root.update()

    extracted_data = extract_features_api(text_to_process, original_text, model_choice)

    if extracted_data:
        if not os.path.exists(FEATURES_DIR):
            os.makedirs(FEATURES_DIR)

        target_folder_name = f"{novel_name}_特征"
        target_folder_path = os.path.join(FEATURES_DIR, target_folder_name)
        if not os.path.exists(target_folder_path):
            os.makedirs(target_folder_path)

        # 映射 JSON 键到中文文件名
        file_mapping = {
            'person_names': '人名库.txt',
            'place_names': '地名库.txt',
            'factions': '势力单位库.txt',
            'power_systems': '力量体系库.txt',
            'internet_slang': '网络词库.txt',
            'keywords': '常规关键词库.txt'
        }

        for key, filename in file_mapping.items():
            file_path = os.path.join(target_folder_path, filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                for word in extracted_data.get(key, []):
                    f.write(word + "\n")

        status_var.set("状态：完成！")
        messagebox.showinfo("成功", f"细化词库文件已生成于：\n{target_folder_name}")
    else:
        status_var.set("状态：API 提取失败。")
        messagebox.showerror("错误", "提取失败。请检查终端报错及网络连接。")

    btn_process.config(state=tk.NORMAL)

# === GUI 界面绘制 ===
root = tk.Tk()
root.title("特征提取与词汇分类工具")
root.geometry("600x400")

folder_path_var = tk.StringVar()
original_file_var = tk.StringVar()
novel_name_var = tk.StringVar()
model_var = tk.StringVar(value="deepseek-chat")
status_var = tk.StringVar(value="状态：等待操作")

tk.Label(root, text="第一步：选择小说统计文件夹").pack(pady=(10, 0))
frame_folder = tk.Frame(root)
frame_folder.pack(fill=tk.X, padx=20)
tk.Entry(frame_folder, textvariable=folder_path_var, state='readonly', width=50).pack(side=tk.LEFT, padx=(0, 10))
tk.Button(frame_folder, text="选择文件夹", command=select_folder).pack(side=tk.LEFT)

tk.Label(root, text="确认小说名称").pack(pady=(5, 0))
tk.Entry(root, textvariable=novel_name_var, width=30).pack()

tk.Label(root, text="第二步：选择小说原文文本 (用于上下文比对)").pack(pady=(10, 0))
frame_original = tk.Frame(root)
frame_original.pack(fill=tk.X, padx=20)
tk.Entry(frame_original, textvariable=original_file_var, state='readonly', width=50).pack(side=tk.LEFT, padx=(0, 10))
tk.Button(frame_original, text="选择原文", command=select_original_file).pack(side=tk.LEFT)

tk.Label(root, text="第三步：选择处理模型").pack(pady=(10, 0))
frame_model = tk.Frame(root)
frame_model.pack()
tk.Radiobutton(frame_model, text="DeepSeek V3 (快速/便宜)", variable=model_var, value="deepseek-chat").pack(side=tk.LEFT, padx=10)
tk.Radiobutton(frame_model, text="DeepSeek R1 (深度推理/耗时)", variable=model_var, value="deepseek-reasoner").pack(side=tk.LEFT, padx=10)

btn_process = tk.Button(root, text="执行分类与提取", command=start_process, bg="lightblue", width=20, height=2)
btn_process.pack(pady=15)

tk.Label(root, textvariable=status_var, fg="gray").pack(side=tk.BOTTOM, pady=5)

if __name__ == "__main__":
    root.mainloop()