import sys
import io
import os
from dotenv import load_dotenv

# 1. 强制重定向标准输出，允许 Windows 控制台处理 Emoji 字符
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 2. 环境变量与模型下载镜像源设置
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
load_dotenv()

# 3. 物理目录架构对齐
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 向上退两级！回到 D:\StyleSync-Novel
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))

# 这样拼接出来的路径就全对了
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")