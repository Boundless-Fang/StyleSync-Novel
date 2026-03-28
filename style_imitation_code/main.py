import os
# 【必须放在最前面】：在导入任何第三方库之前，强行设置全局镜像源！
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 针对 Windows 强制禁用软链接，解决 WinError 14007 错误
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
# 预设模型缓存路径，有时能绕过权限问题
# 修改为自定义路径，注意 Windows 路径使用双反斜杠或前缀 r
os.environ["HUGGINGFACE_HUB_CACHE"] = r"D:\StyleSync-Novel\huggingface\hub"

import sys
import io
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # 新增导入

# 从拆分出来的 api 包中引入挂载好的 router
from api import router
from api.config import CODE_DIR  # 新增导入

# 强制重定向标准输出，允许 Windows 控制台处理 Emoji 字符
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

app = FastAPI(title="DeepSeek Ultimate Pro + Writer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载全部路由
app.include_router(router)

# 新增：挂载前端静态文件目录
# 注意：一定要放在 include_router 之后，避免覆盖 API 路由
app.mount("/", StaticFiles(directory=os.path.join(CODE_DIR, "frontend"), html=True), name="frontend")

if __name__ == "__main__":
    # 改回了原版的启动写法，保证在任意目录运行都不会报模块错误
    uvicorn.run(app, host="0.0.0.0", port=8000)