import sys
import io
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 从拆分出来的 api 包中引入挂载好的 router
from api.routes import router

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

if __name__ == "__main__":
    # 改回了原版的启动写法，保证在任意目录运行都不会报模块错误
    uvicorn.run(app, host="0.0.0.0", port=8000)