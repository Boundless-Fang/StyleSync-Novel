import os

# 【关键配置】：在导入模型库之前，强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# --- 1. 路径定义 --- 
# 修改前：只退了 2 层，定位到了 style_imitation_code 
# PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
 
# 修改后：退 3 层，精准定位到 D:\StyleSync-Novel 
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) 

# --- 2. 映射实际物理文件夹 ---
CODE_DIR = os.path.join(PROJECT_ROOT, "style_imitation_code")
REF_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")
DICT_DIR = os.path.join(PROJECT_ROOT, "dictionaries")
TEST_DIR = os.path.join(PROJECT_ROOT, "text_testing_code")

# --- 3. 兜底检测与创建 ---
for directory in [CODE_DIR, REF_DIR, STYLE_DIR, PROJ_DIR, DICT_DIR, TEST_DIR]:
    os.makedirs(directory, exist_ok=True)