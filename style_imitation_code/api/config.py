import os

# 【关键配置】：在导入模型库之前，强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# --- 1. 物理目录架构严格对齐文档 ---
# 因为 config.py 在 api/ 下面，所以往上退三层到达项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CODE_DIR = os.path.join(PROJECT_ROOT, "style_imitation_code")
REF_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")
DICT_DIR = os.path.join(PROJECT_ROOT, "dictionaries")
TEST_DIR = os.path.join(PROJECT_ROOT, "text_testing_code")

for directory in [CODE_DIR, REF_DIR, STYLE_DIR, PROJ_DIR, DICT_DIR, TEST_DIR]:
    os.makedirs(directory, exist_ok=True)