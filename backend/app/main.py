import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.routes import assessment, auth, courses, projects, course_search, graph, chat, curriculum

# 載入 .env（開發環境）
load_dotenv(Path(__file__).parent.parent.parent / ".env")

logger = logging.getLogger(__name__)


def get_allowed_origins() -> list[str]:
    origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://localhost:3000,"
        "http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:3000",
    )
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────
    try:
        from app.agents.pdf.runner import setup_checkpointer
        await setup_checkpointer()
        logger.info("PDF chat checkpointer ready")
    except Exception as exc:
        logger.warning("PDF chat checkpointer setup failed (continuing): %s", exc)

    try:
        from app.services.pdf_memory_service import ensure_memory_collection
        await ensure_memory_collection()
        logger.info("PDF memory collection ready")
    except Exception as exc:
        logger.warning("PDF memory collection setup failed (continuing): %s", exc)

    yield

    # ── Shutdown ───────────────────────────────────────────────
    try:
        from app.agents.pdf.research.agent import _background_tasks, request_all_drain
        request_all_drain("shutdown")
        if _background_tasks:
            await asyncio.gather(*_background_tasks, return_exceptions=True)
    except Exception as exc:
        logger.warning("PDF research shutdown error: %s", exc)

    try:
        from app.agents.pdf.runner import shutdown_checkpointer
        await shutdown_checkpointer()
    except Exception as exc:
        logger.warning("PDF chat checkpointer shutdown error: %s", exc)


app = FastAPI(
    title="NCU High School Student Portal API",
    description="API for NCU high school student guidance system",
    version="1.0.0",
    lifespan=lifespan,
)

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
