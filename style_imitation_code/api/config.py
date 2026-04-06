# --- File: api/config.py ---
import os

# 从项目根目录的新建文件中直接引入已计算好的绝对路径
from paths_config import (
    PROJECT_ROOT, 
    CODE_DIR, 
    REF_DIR, 
    STYLE_DIR, 
    PROJ_DIR, 
    DICT_DIR, 
    TEST_DIR
)

# 【关键配置】：在导入模型库之前，强制设置 HuggingFace 国内镜像源环境
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"