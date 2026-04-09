import os
import socket
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 【必须放在最前面】：在导入任何第三方库之前，强行设置全局镜像源！
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 针对 Windows 强制禁用软链接，解决 WinError 14007 错误
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
# 预设模型缓存路径，有时能绕过权限问题
os.environ["HUGGINGFACE_HUB_CACHE"] = r"D:\StyleSync-Novel\huggingface\hub"

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api import router
from api.config import CODE_DIR

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

# ================= 核心修改区 =================
# 1. 静态资源（js, css）必须移到 /static 路径下
app.mount("/static", StaticFiles(directory=os.path.join(CODE_DIR, "frontend")), name="static")

# 2. 声明 Jinja2 模板引擎目录
templates = Jinja2Templates(directory=os.path.join(CODE_DIR, "frontend"))

# 3. 根路由交给模板引擎，它会自动把 components 里的 html 拼装好再发给浏览器
@app.get("/")
async def serve_frontend(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
# ==============================================

@app.on_event("startup")
async def startup_event():
    print("\n" + "="*60)
    print("[系统通知] Web 服务及底层通信引擎已启动")
    print("[界面访问] 请在浏览器中点击或输入以下地址访问工作台：")
    print(" 👉 本机访问: http://127.0.0.1:8000")
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
        print(f" 👉 局域网访问: http://{lan_ip}:8000")
    except Exception:
        pass
    print("="*60 + "\n")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)