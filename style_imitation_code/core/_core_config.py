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

# 3. 根目录定义 
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # 这是 core/ 目录 
 
# 修改前：只退了 1 层，定位到了 style_imitation_code 
# PROJECT_ROOT = os.path.dirname(BASE_DIR) 
 
# 修改后：退 2 层，精准定位到 D:\StyleSync-Novel 
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR)) 

# 4. 映射实际物理文件夹
CODE_DIR = os.path.join(PROJECT_ROOT, "style_imitation_code")
REFERENCE_DIR = os.path.join(PROJECT_ROOT, "reference_novels")
STYLE_DIR = os.path.join(PROJECT_ROOT, "text_style_imitation")
PROJ_DIR = os.path.join(PROJECT_ROOT, "novel_projects")
DICT_DIR = os.path.join(PROJECT_ROOT, "dictionaries")
TEST_DIR = os.path.join(PROJECT_ROOT, "text_testing_code")

# 5. 兜底检测与创建 (保持与 api 层一致性)
for directory in [CODE_DIR, REFERENCE_DIR, STYLE_DIR, PROJ_DIR, DICT_DIR, TEST_DIR]:
    os.makedirs(directory, exist_ok=True)