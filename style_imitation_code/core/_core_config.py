# --- File: core/_core_config.py ---
import os
from dotenv import load_dotenv

# 从项目根目录的新建文件中直接引入路径
from paths_config import (
    PROJECT_ROOT, 
    CODE_DIR, 
    REF_DIR, 
    STYLE_DIR, 
    PROJ_DIR, 
    DICT_DIR, 
    TEST_DIR
)

# 兼容旧代码的历史遗留命名习惯
REFERENCE_DIR = REF_DIR
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # 保留指向 core/ 的指针供老逻辑使用

# 环境变量与模型下载镜像源设置
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
load_dotenv()