from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web" / "static"

app = FastAPI(title="澳门彩生肖助手", version="1.0.0")
app.include_router(router)

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
def index():
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        return {"message": "前端未就绪"}
    return FileResponse(index_file)
