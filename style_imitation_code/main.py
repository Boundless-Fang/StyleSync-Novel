import os
import socket  # 新增导入用于自动获取局域网IP
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 【必须放在最前面】：在导入任何第三方库之前，强行设置全局镜像源！
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 针对 Windows 强制禁用软链接，解决 WinError 14007 错误
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
# 预设模型缓存路径，有时能绕过权限问题
# 修改为自定义路径，注意 Windows 路径使用双反斜杠或前缀 r
os.environ["HUGGINGFACE_HUB_CACHE"] = r"D:\StyleSync-Novel\huggingface\hub"

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # 新增导入

# 从拆分出来的 api 包中引入挂载好的 router
from api import router
from api.config import CODE_DIR  # 新增导入

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

# 新增：挂载应用启动事件，解析并打印易于点击的真实访问地址
@app.on_event("startup")
async def startup_event():
    print("\n" + "="*60)
    print("[系统通知] Web 服务及底层通信引擎已启动")
    print("[界面访问] 请在浏览器中点击或输入以下地址访问工作台：")
    print(" 👉 本机访问: http://127.0.0.1:8000")
    
    # 容错处理：尝试探测真实局域网 IP
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