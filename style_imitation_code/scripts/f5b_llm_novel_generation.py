import os
import re

import numpy as np

from core._core_cli_runner import HeadlessBaseTask, inject_env, safe_run_app
from core._core_config import PROJ_DIR
from core._core_llm import stream_deepseek_api
from core._core_rag import RAGRetriever
from core._core_utils import atomic_write, smart_read_text

inject_env()


class NovelGenerationApp(HeadlessBaseTask):
    def __init__(self):
        super().__init__()

    def execute_logic(self):
        pass

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
        arabic_match = re.search(r"\d+", name or "")
        if arabic_match:
            return int(arabic_match.group(0))

        cn_match = re.search(r"第?([零一二两三四五六七八九十百千万]+)[章节回卷]", name or "")
        if cn_match:
            cn_num = cn_match.group(1)
            cn_map = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
            cn_units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
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
        return 999999

    @staticmethod
    def get_previous_context(content_dir, current_chapter_name):
        if not os.path.exists(content_dir):
            return ""

        chapters = [f for f in os.listdir(content_dir) if f.endswith(".txt")]
        if not chapters:
            return ""

        current_num = NovelGenerationApp.get_chapter_number(current_chapter_name)
        prev_chapters = [f for f in chapters if NovelGenerationApp.get_chapter_number(f) < current_num]
        if not prev_chapters:
            return ""

        prev_chapters.sort(key=NovelGenerationApp.get_chapter_number, reverse=True)
        last_chapter_path = os.path.join(content_dir, prev_chapters[0])
        content = NovelGenerationApp.read_file_safe(last_chapter_path)
        return content[-1000:] if len(content) > 1000 else content

    @staticmethod
    def parse_outline_layers(chapter_outline):
        text = chapter_outline or ""
        position_match = re.search(
            r"#\s*第一层：本章定位\s*(.*?)(?=\n#\s*第二层：本章结构|\Z)",
            text,
            re.S,
        )
        structure_match = re.search(
            r"#\s*第二层：本章结构\s*(.*)",
            text,
            re.S,
        )
        position_text = position_match.group(1).strip() if position_match else ""
        structure_text = structure_match.group(1).strip() if structure_match else ""
        return position_text, structure_text

    @staticmethod
    def parse_position_value(position_text, key):
        pattern = rf"-\s*{re.escape(key)}\s*：\s*(.+)"
        match = re.search(pattern, position_text)
        return match.group(1).strip() if match else ""

    @staticmethod
    def parse_character_names(position_text):
        raw_value = NovelGenerationApp.parse_position_value(position_text, "出场角色")
        if not raw_value:
            return []
        names = re.split(r"[,，、/／\s]+", raw_value)
        return [name.strip() for name in names if name.strip() and name.strip() not in {"无", "未指定"}]

    @staticmethod
    def get_filtered_characters(target_dir, explicit_characters, fallback_text, log_func):
        char_dir = os.path.join(target_dir, "character_profiles")
        if not os.path.exists(char_dir):
            return "无相关角色卡数据。"

        all_char_files = [f for f in os.listdir(char_dir) if f.endswith(".md")]
        relevant_texts = []
        found_names = []
        scan_text = fallback_text or ""

        for f_name in all_char_files:
            char_name_base = os.path.splitext(f_name)[0]
            matched = char_name_base in explicit_characters or char_name_base in scan_text
            if matched:
                content = NovelGenerationApp.read_file_safe(os.path.join(char_dir, f_name))
                if content:
                    relevant_texts.append(content)
                    found_names.append(char_name_base)

        if not relevant_texts:
            log_func("[WARN] 未匹配到明确角色卡，正文将主要依赖世界观和大纲执行。")
            return "本章未匹配到明确角色卡。"

        log_func(f"[INFO] 已注入本章角色卡: {', '.join(found_names)}")
        return "\n\n---\n\n".join(relevant_texts)

    @staticmethod
    def retrieve_context(index_path, chunks_path, retriever, query_vec, k_limit):
        try:
            index, chunks = retriever.load_index(index_path, chunks_path)
            distances, indices = index.search(np.array(query_vec).astype("float32"), k=k_limit)
            retrieved_data = []
            for idx in indices[0]:
                if idx != -1 and idx < len(chunks):
                    chunk_item = chunks[idx]
                    if isinstance(chunk_item, dict):
                        retrieved_data.append(
                            chunk_item.get("summary", chunk_item.get("raw_chunk", chunk_item.get("text", "")))
                        )
                    else:
                        retrieved_data.append(chunk_item)
            return retrieved_data
        except Exception:
            return []

    @staticmethod
    def build_rag_context(target_dir, query_text, log_func):
        rag_context_original = "无原著参考片段。"
        rag_context_project = "无项目记忆片段。"

        try:
            retriever = RAGRetriever()
            embedder = retriever.get_embedder()
            query_vec = embedder.encode([query_text[:1500] if query_text else "本章正文生成"])

            hierarchical_db = os.path.join(target_dir, "hierarchical_rag_db")
            if os.path.exists(hierarchical_db):
                idx_path = os.path.join(hierarchical_db, "plot_summary.index")
                map_path = os.path.join(hierarchical_db, "summary_to_raw_mapping.json")
                res = NovelGenerationApp.retrieve_context(idx_path, map_path, retriever, query_vec, k_limit=2)
                if res:
                    rag_context_original = "\n\n".join(res)

            context_db = os.path.join(target_dir, "context_rag_db")
            if os.path.exists(context_db):
                idx_path = os.path.join(context_db, "vector.index")
                map_path = os.path.join(context_db, "chunks.json")
                res = NovelGenerationApp.retrieve_context(idx_path, map_path, retriever, query_vec, k_limit=4)
                if res:
                    rag_context_project = "\n\n---\n\n".join(res)
        except Exception as e:
            log_func(f"[WARN] f5b RAG 检索失败，已降级继续: {e}")

        return rag_context_original, rag_context_project

    @staticmethod
    def execute_generation(project_name, chapter_name, model, log_func, export_prompt_only=False):
        target_dir = os.path.join(PROJ_DIR, project_name)
        if not os.path.exists(target_dir):
            log_func(f"[ERROR] 未找到项目目录: {target_dir}")
            return False

        outline_path = os.path.join(target_dir, "chapter_structures", f"{chapter_name}_outline.md")
        chapter_outline = NovelGenerationApp.read_file_safe(outline_path)
        if not chapter_outline:
            log_func(f"[ERROR] 未找到本章大纲文件: {outline_path}，请先执行 f5a。")
            return False

        position_text, structure_text = NovelGenerationApp.parse_outline_layers(chapter_outline)
        explicit_characters = NovelGenerationApp.parse_character_names(position_text)

        log_func("正在加载 f5b 生成所需的世界观、角色卡与文风摘要...")
        world_settings = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "world_settings.md")) or "无详细世界观。"
        style_summary = NovelGenerationApp.read_file_safe(os.path.join(target_dir, "features.md"), max_len=1800) or "无明确文风摘要。"
        characters_info = NovelGenerationApp.get_filtered_characters(target_dir, explicit_characters, chapter_outline, log_func)

        log_func("正在抽取上一章结尾原文承接点...")
        content_dir = os.path.join(target_dir, "content")
        os.makedirs(content_dir, exist_ok=True)
        previous_context = NovelGenerationApp.get_previous_context(content_dir, chapter_name)

        log_func("正在检索与本章相关的 RAG 参考...")
        rag_context_original, rag_context_project = NovelGenerationApp.build_rag_context(
            target_dir, f"{position_text}\n{structure_text}", log_func
        )

        system_prompt = f"""你是一个专业的网络小说作者。你的任务是基于给定的章节定位与章节结构，生成一章完整、自然、具有网络小说阅读感的正文。

你必须严格遵守以下规则：
1. 必须服从 f5a 生成的本章定位和本章结构，不允许擅自改写章节功能或越界推进到下一章。
2. 必须遵守世界观和角色卡，不允许人物明显 OOC，不允许违背底层设定。
3. 上一章结尾原文用于“句子级承接”，RAG 用于“背景与记忆补充”，两者都不能被忽视。
4. 文风摘要只作为倾向性约束，不要机械堆砌词汇或套用分析术语。
5. 直接输出小说正文，不要输出解释、标题、结构说明或任何额外提示。
6. 正文默认控制在 3000 字左右，可根据大纲中的字数安排自然浮动。

[文风摘要]
{style_summary}

[世界观]
{world_settings}

[角色卡]
{characters_info}

[RAG - 原著相关片段]
{rag_context_original}

[RAG - 前文记忆片段]
{rag_context_project}
"""

        user_prompt = f"""[f5a 第一层：本章定位]
{position_text or "无明确本章定位，请严格依照章节名与整体语境谨慎生成。"}

[f5a 第二层：本章结构]
{structure_text or "无明确本章结构，请尽量按照起承转合组织正文。"}

[上一章结尾原文（允许为空）]
{previous_context or "无上一章结尾原文。"}

请严格按照以上信息生成本章正文。"""

        if export_prompt_only:
            print(f"=== System Prompt ===\n{system_prompt}\n\n=== User Prompt ===\n{user_prompt}")
            return True

        prompt_dir = os.path.join(target_dir, "chapter_specific_prompts")
        os.makedirs(prompt_dir, exist_ok=True)
        prompt_filepath = os.path.join(prompt_dir, f"prompt_{chapter_name}.txt")
        try:
            prompt_content = f"=== System Prompt ===\n{system_prompt}\n\n=== User Prompt ===\n{user_prompt}\n"
            atomic_write(prompt_filepath, prompt_content, data_type="text")
            log_func(f"已将本章最终指令保存至: {prompt_filepath}")
        except Exception as e:
            log_func(f"保存指令文件失败: {str(e)}")

        log_func("\n>> 提示词构建完毕，正在执行流式正文生成...\n")
        output_filepath = os.path.join(content_dir, f"{chapter_name}.txt")
        try:
            full_content = ""
            for chunk in stream_deepseek_api(system_prompt, user_prompt, model, temperature=0.5):
                log_func(chunk, append=True)
                full_content += chunk
            atomic_write(output_filepath, full_content, data_type="text")
            log_func(f"\n\n[INFO] 章节正文生成完毕，已保存至: {output_filepath}")
            return True
        except Exception as e:
            log_func(f"\n[ERROR] 流式生成中断或失败: {str(e)}")
            import traceback

            traceback.print_exc()
            return False


def run_headless(project_name, chapter_name, model="deepseek-chat", export_prompt_only=False):
    import sys

    if not project_name or not chapter_name:
        sys.exit(1)
    if not export_prompt_only:
        print(f"开始静默执行小说流式生成: 项目 [{project_name}] - 章节 [{chapter_name}]")
    success = NovelGenerationApp.execute_generation(
        project_name,
        chapter_name,
        model,
        lambda msg, append=False: print(msg, end="" if append else "\n", flush=True)
        if not export_prompt_only
        else None,
        export_prompt_only=export_prompt_only,
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    safe_run_app(
        app_class=NovelGenerationApp,
        headless_func=run_headless,
        project_name="",
        chapter_name="",
        model="",
    )
