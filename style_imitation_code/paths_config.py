# --- File: paths_config.py ---
import os

# 1. 精准定位当前文件所在目录 (D:\StyleSync-Novel\style_imitation_code)
CODE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 向上退 1 层，精准锁定总根目录 (D:\StyleSync-Novel)
PROJECT_ROOT = os.path.dirname(CODE_DIR)

# 3. 映射所有实际物理文件夹
REF_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")
DICT_DIR = os.path.join(PROJECT_ROOT, "dictionaries")
TEST_DIR = os.path.join(PROJECT_ROOT, "text_testing_code")

# 4. 统一兜底检测与创建，系统启动时只执行一次
for directory in [CODE_DIR, REF_DIR, STYLE_DIR, PROJ_DIR, DICT_DIR, TEST_DIR]:
    os.makedirs(directory, exist_ok=True)