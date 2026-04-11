import os
import json

from core._core_cli_runner import safe_run_app, inject_env, HeadlessBaseTask
inject_env()

from core._core_config import PROJ_DIR
from core._core_utils import smart_read_text, atomic_write
from core._core_llm import call_deepseek_api
from core._core_rag import RAGRetriever
import numpy as np

class ChapterOutlineApp(HeadlessBaseTask):
    def __init__(self):
        super().__init__()

    def execute_logic(self):
        pass # 此方法已完全交由 Web API 层通过 run_headless 静默执行

    @staticmethod
    def read_file_safe(filepath, max_len=None):
        if os.path.exists(filepath):
            try:
                return smart_read_text(filepath, max_len=max_len)
            except Exception:
                return ""
        return ""

    @staticmethod
    def get_filtered_characters(target_dir, chapter_brief, log_func):
        char_dir = os.path.join(target_dir, "character_profiles")
        if not os.path.exists(char_dir):
            return "无相关角色卡数据。"
        
        all_char_files = [f for f in os.listdir(char_dir) if f.endswith(".md")]
        relevant_texts = []
        found_names = []

        for f_name in all_char_files:
            char_name_base = os.path.splitext(f_name)[0]
            if char_name_base in chapter_brief:
                content = ChapterOutlineApp.read_file_safe(os.path.join(char_dir, f_name))
                if content:
                    relevant_texts.append(content)
                    found_names.append(char_name_base)
        
        if not relevant_texts:
            log_func("[INFO] 未在简述中检测到特定角色名，将跳过角色卡注入，防止 OOM。")
            return "本章节未提及特定已知角色卡中的人物。"
        
        log_func(f"[INFO] 严格匹配命中关键角色: {', '.join(found_names)}，已成功注入其专属角色卡。")
        return "\n\n---\n\n".join(relevant_texts)

    @staticmethod
    def retrieve_context(index_path, chunks_path, retriever, query_vec, k_limit):
        try:
            index, chunks = retriever.load_index(index_path, chunks_path)
            distances, indices = index.search(np.array(query_vec).astype('float32'), k=k_limit)
            
            retrieved_data = []
            for idx in indices[0]:
                if idx != -1 and idx < len(chunks):
                    chunk_item = chunks[idx]
                    if isinstance(chunk_item, dict):
                        retrieved_data.append(chunk_item.get("summary", chunk_item.get("raw_chunk", chunk_item.get("text", ""))))
                    else:
                        retrieved_data.append(chunk_item)
            return retrieved_data
        except Exception:
            return []

    @staticmethod
    def execute_generation(project_name, chapter_name, chapter_brief, model, log_func):
        target_dir = os.path.join(PROJ_DIR, project_name)
        if not os.path.exists(target_dir):
            log_func(f"[ERROR] 错误: 未找到项目目录 {target_dir}")
            return False
            
        outlines_dir = os.path.join(target_dir, "chapter_structures")
        os.makedirs(outlines_dir, exist_ok=True)
        save_path = os.path.join(outlines_dir, f"{chapter_name}_outline.md")

        # 1. 静态加载设定
        world_settings = ChapterOutlineApp.read_file_safe(os.path.join(target_dir, "world_settings.md")) or "无详细世界观。"
        characters_info = ChapterOutlineApp.get_filtered_characters(target_dir, chapter_brief, log_func)

        # 2. 双轨 RAG 检索
        rag_context_original = "无原著背景库参考。"
        rag_context_project = "无前文剧情记忆。"
        
        try:
            retriever = RAGRetriever()
            embedder = retriever.get_embedder()
            query_vec = embedder.encode([chapter_brief]) 
            
            hierarchical_db = os.path.join(target_dir, "hierarchical_rag_db")
            if os.path.exists(hierarchical_db):
                log_func("检测到同人原著参考库，正在提取背景环境...")
                idx_path = os.path.join(hierarchical_db, "plot_summary.index")
                map_path = os.path.join(hierarchical_db, "summary_to_raw_mapping.json")
                res = ChapterOutlineApp.retrieve_context(idx_path, map_path, retriever, query_vec, k_limit=2)
                if res: rag_context_original = "\n\n".join(res)

            context_db = os.path.join(target_dir, "context_rag_db")
            if os.path.exists(context_db):
                log_func("检测到当前项目前文 RAG 库，正在恢复剧情记忆...")
                idx_path = os.path.join(context_db, "vector.index")
                map_path = os.path.join(context_db, "chunks.json")
                res = ChapterOutlineApp.retrieve_context(idx_path, map_path, retriever, query_vec, k_limit=4)
                if res: rag_context_project = "\n\n---\n\n".join(res)
            else:
                log_func("[WARN] 未检测到 context_rag_db，可能遭遇断层。建议前往工作台执行一次 f4c 构建前文记忆。")
        except Exception as e:
            log_func(f"[WARN] 双轨 RAG 模块非致命异常，已执行降级绕过: {e}")

        # 3. 构建 Prompt 并请求大模型
        prompt_header = """你是一个顶级网文编剧。请根据以下信息，为用户输入的“本章核心简述”扩写一份【逻辑极其严密、冲突激烈、节奏紧凑】的章节大纲。

### 核心任务与边界清单（绝密指令）：
1. 剧情密度控制（Density Control）：如果用户提供的简述包含了过多的事件转折，请强行放缓节奏！你只需重点扩写简述中的【前一到两个核心事件】，剩余事件全部砍掉，留作下一章的悬念。绝不允许把剧情写成走马观花的流水账。
2. 剧情边界锁死（Boundary Lock）：必须且只能在用户简述的进度处停止！绝不允许擅自推进后续剧情，绝不允许凭空引入简述中未提及的怪物、新人物或大场面。
3. 人物对齐：必须符合所提供的角色卡性格与力量等级，增加言语试探与心理博弈，禁止一上来就无脑放法宝互砸。

请严格按以下 Markdown 格式输出：

### 一、 核心要素
- **写作目的**：
- **场景分布**：（场景一、场景二...）
- **核心冲突**：

### 二、 细化大纲
- **开篇（衔接前文）**：[具体描写环境与氛围]
- **发展（矛盾升级）**：[此阶段必须包含多轮人物对话交锋与试探，严禁直接进入纯动作战斗]
- **高潮（核心冲突）**：[具体描写，含情绪指令与动作拆解]
- **结尾（悬念钩子）**：[具体描写，卡在最高潮或悬念处戛然而止，为下一章留扣]

### 三、 细节注意
- **关键动作建议**：
- **雷点/禁忌**：

---
【基础设定与上下文矩阵】：
"""
        user_input = f"""{prompt_header}
[世界观与底层设定]
{world_settings}

[出场关键角色卡]
{characters_info}

[原著参考线索 (仅提供氛围与基础设定供参考，禁止完全照抄剧情)]
{rag_context_original}

[本书前文记忆剧情 (用于无缝衔接前章进度)]
{rag_context_project}

[用户本章简述]
{chapter_brief}
"""
        sys_prompt = "你是一个专业的小说大纲设计师，严禁废话，必须严格锁死剧情边界，只输出 Markdown。"

        try:
            log_func("正在连接 DeepSeek 执行深度大纲推演...")
            result_text = call_deepseek_api(system_prompt=sys_prompt, user_prompt=user_input, model=model, temperature=0.6)
            
            atomic_write(save_path, result_text, data_type='text')
            log_func(f"[INFO] 架构生成成功！大纲已原子级落盘至: {save_path}")
            return True
        except Exception as e:
            log_func(f"[ERROR] 接口请求失败: {str(e)}")
            return False

def run_headless(project_name, chapter_name, chapter_brief_json, model="deepseek-chat"):
    import sys
    try:
        data = json.loads(chapter_brief_json)
        chapter_brief = data.get("brief", "")
    except Exception:
        chapter_brief = chapter_brief_json

    if not project_name or not chapter_name:
        sys.exit(1)
        
    print(f"静默生成大纲中: {project_name} - {chapter_name}")
    success = ChapterOutlineApp.execute_generation(project_name, chapter_name, chapter_brief, model, print)
    if not success: sys.exit(1)

if __name__ == "__main__":
    safe_run_app(
        app_class=ChapterOutlineApp,
        headless_func=run_headless,
        project_name="",
        chapter_name="",
        chapter_brief_json="",
        model=""
    )
