import os
import json
import shutil

from core._core_cli_runner import safe_run_app, inject_env, HeadlessBaseTask
inject_env()

from core._core_config import BASE_DIR, PROJECT_ROOT, REFERENCE_DIR, STYLE_DIR, PROJ_DIR
from core._core_llm import call_deepseek_api
from core._core_utils import atomic_write
from core._core_rag import RAGRetriever

class SettingCompletionApp(HeadlessBaseTask):
    def __init__(self):
        super().__init__()

    def execute_logic(self):
        pass # 此方法已完全交由 Web API 层通过 run_headless 静默执行

    @staticmethod
    def execute_completion(original_path, mode, json_data, model, log_func, project_name=None):
        log_func(f"正在进行【{mode}】模式设定补全 (RAG 加速版)...")
        
        target_dir = PROJ_DIR
        if project_name:
            target_dir = os.path.join(PROJ_DIR, project_name)
            os.makedirs(target_dir, exist_ok=True)

        if not original_path:
             log_func("[ERROR] 错误：未提供参考原文路径，无法定位 RAG 索引。")
             return False
             
        novel_name = os.path.splitext(os.path.basename(original_path))[0]
        style_dir = os.path.join(STYLE_DIR, f"{novel_name}_style_imitation")
        rag_db_dir = os.path.join(style_dir, "global_rag_db")
        
        index_path = os.path.join(rag_db_dir, "vector.index")
        chunks_path = os.path.join(rag_db_dir, "chunks.json")

        if not os.path.exists(index_path) or not os.path.exists(chunks_path):
             log_func("[ERROR] 致命错误：未找到全局 RAG 索引。请先执行 f0 初始化！")
             return False

        log_func("正在加载全局 RAG 索引...")
        try:
            retriever = RAGRetriever()
            index, chunks = retriever.load_index(index_path, chunks_path)
            log_func(f"已加载索引，包含 {len(chunks)} 个文本块。")
        except Exception as e:
            log_func(f"[ERROR] 索引加载失败: {str(e)}")
            return False

        queries = []
        if mode == "worldview":
            for key, value in json_data.items():
                if value and str(value).strip():
                     queries.append(str(value).strip())
            queries.extend(["世界观", "力量体系", "境界", "宗门", "历史", "传说", "地图", "势力"])
            
        elif mode == "character":
            char_name = json_data.get("name", "")
            if char_name:
                queries.append(char_name)
                queries.extend([
                    f"{char_name} 外貌", f"{char_name} 性格", f"{char_name} 身份", 
                    f"{char_name} 说话", f"{char_name} 战斗", f"{char_name} 经历"
                ])
            for key, value in json_data.items():
                if value and str(value).strip() and key != "name":
                    queries.append(str(value).strip())

        log_func(f"正在基于 {len(queries)} 个关键信息点进行 RAG 检索...")
        try:
            retrieved_chunks = retriever.search(index, chunks, queries, k=5, batch_size=5)
            context_text = "\n...\n".join(retrieved_chunks[:40]) 
            log_func(f"成功召回 {min(len(retrieved_chunks), 40)} 个高相关度片段。")
            
        except Exception as e:
            log_func(f"[ERROR] RAG 检索失败: {str(e)}")
            return False

        if mode == "worldview":
            save_path = os.path.join(target_dir, "world_settings.md")
            prompt_header = """【系统指令】：
用户提供了小说的部分世界观设定。请你阅读参考文本，结合用户已给出的设定，将其余空缺部分补全。
如果有无法从文本中得出的信息，请基于小说的基础逻辑进行合理推演，并在补全项后标注“（推演补全）”。
必须输出完整的 Markdown 结构。

【用户已提供的设定】：
"""
            prompt = prompt_header + json.dumps(json_data, ensure_ascii=False, indent=2) + "\n\n【参考原文片段 (RAG 检索)】：\n" + context_text

        elif mode == "character":
            char_name = json_data.get("name", "未知角色")
            char_dir = os.path.join(target_dir, "character_profiles")
            os.makedirs(char_dir, exist_ok=True)
            save_path = os.path.join(char_dir, f"{char_name}.md")
            prompt_header = f"""【系统指令】：
用户提供了角色【{char_name}】的部分设定。请结合原文片段，补全该角色缺失的信息（包括未填写的相关信息、价值观排序、语言习惯等）。
必须严格遵循原文，如果在文本中确实没有提及，请填“未知”。必须使用标准的 Markdown 结构输出全套角色信息卡。

【用户已提供的部分设定】：
"""
            prompt = prompt_header + json.dumps(json_data, ensure_ascii=False, indent=2) + "\n\n【参考原文片段 (RAG 检索)】：\n" + context_text

        sys_prompt = "你是一个严谨的设定补全专家。只允许输出 Markdown 格式的纯文本。"

        try:
            result_text = call_deepseek_api(system_prompt=sys_prompt, user_prompt=prompt, model=model, temperature=0.4)
            atomic_write(save_path, result_text, data_type='text')
            log_func(f"[INFO] 补全完成！文件已原子级落盘至: {save_path}")
            return True
        except Exception as e:
            log_func(f"[ERROR] API 调用失败: {str(e)}")
            return False

def run_headless(target_file, mode, json_data, project_name=None, model="deepseek-chat"):
    import sys
    if isinstance(json_data, str):
        try:
            json_data = json.loads(json_data)
        except json.JSONDecodeError:
            print("error: json_data 解析失败")
            sys.exit(1)
        
    print(f"开始静默执行设定补全 (模式: {mode})")
    success = SettingCompletionApp.execute_completion(target_file, mode, json_data, model, print, project_name)
    if not success: sys.exit(1)

if __name__ == "__main__":
    safe_run_app(
        app_class=SettingCompletionApp,
        headless_func=run_headless,
        target_file="",
        mode="",
        json_data="",
        project_name="",
        model=""
    )
