import os
import socket

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import router
from api.config import CODE_DIR
from core._core_config import load_project_env

load_project_env()

app = FastAPI(title="DeepSeek Ultimate Pro + Writer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.mount("/static", StaticFiles(directory=os.path.join(CODE_DIR, "frontend")), name="static")


@app.get("/")
async def serve_frontend():
    html_path = os.path.join(CODE_DIR, "frontend", "index.html")
    return FileResponse(html_path)


@app.on_event("startup")
async def startup_event():
    print("\n" + "=" * 60)
    print("[System] Web service started successfully.")
    print("[Access] Open the app in your browser:")
    print(" -> Local: http://127.0.0.1:8000")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        lan_ip = sock.getsockname()[0]
        sock.close()
        print(f" -> LAN: http://{lan_ip}:8000")
    except Exception:
        pass

    print("=" * 60 + "\n")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
