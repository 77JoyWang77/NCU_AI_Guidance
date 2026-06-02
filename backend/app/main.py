import os
import re
import time
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from app.routes import assessment, auth, courses, projects, course_search, graph, chat, curriculum, monitor
from app.services import latency_store as ls

# 載入 .env（開發環境）
load_dotenv(Path(__file__).parent.parent.parent / ".env")


def get_allowed_origins() -> list[str]:
    origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://localhost:3000,"
        "http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:3000",
    )
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


_DYNAMIC_RE = re.compile(r"/[0-9a-f]{8,}|/\d+")
_SKIP_PREFIXES = ("/health", "/docs", "/openapi", "/pdfs", "/redoc")


def _normalize_path(path: str) -> str:
    return _DYNAMIC_RE.sub("/{id}", path)


class LatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)
        t0 = time.perf_counter()
        response = await call_next(request)
        ls.record_request(
            _normalize_path(request.url.path),
            (time.perf_counter() - t0) * 1000,
            response.status_code,
        )
        return response


app = FastAPI(
    title="NCU High School Student Portal API",
    description="API for NCU high school student guidance system",
    version="1.0.0"
)

app.add_middleware(LatencyMiddleware)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(assessment.router, prefix="/api/assessment", tags=["assessment"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(courses.router, prefix="/api/courses", tags=["courses"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(course_search.router, prefix="/api/course-search", tags=["course-search"])
app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(curriculum.router, prefix="/api/curriculum", tags=["curriculum"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"])

# 掛載 PDF 靜態文件服務
pdf_directory = Path(__file__).parent.parent.parent / "data" / "raw" / "projects" / "104-114"
if pdf_directory.exists():
    app.mount("/pdfs", StaticFiles(directory=str(pdf_directory)), name="pdfs")

@app.get("/")
async def root():
    return {
        "message": "NCU High School Student Portal API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
