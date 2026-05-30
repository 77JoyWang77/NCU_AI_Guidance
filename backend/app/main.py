import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.routes import assessment, auth, courses, projects, course_search, graph, chat, curriculum
from app.logging_config import configure_logging

configure_logging()

# 載入 .env（開發環境）
load_dotenv(Path(__file__).parent.parent.parent / ".env")

logger = logging.getLogger(__name__)

_pdf_init_ready = False
_rag_init_ready = False


def get_allowed_origins() -> list[str]:
    origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://localhost:3000,"
        "http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:3000",
    )
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # PDF chat coordination (stream lock, cancel, steering) is process-local.
    # This application MUST run as a single Uvicorn worker (--workers 1).
    # Multi-worker support requires migrating these to PostgreSQL LISTEN/NOTIFY.
    workers = os.getenv("WEB_CONCURRENCY", os.getenv("UVICORN_WORKERS", "1"))
    if str(workers) != "1":
        logger.warning(
            "SINGLE-WORKER VIOLATION: WEB_CONCURRENCY=%s detected. "
            "PDF chat stream lock, cancel, and steering are process-local and will malfunction "
            "with multiple workers. Set WEB_CONCURRENCY=1 or --workers 1.",
            workers,
        )

    global _pdf_init_ready
    pdf_ok = False

    # PDF 問答初始化
    try:
        from app.agents.pdf.runner import setup_checkpointer
        await setup_checkpointer()
        pdf_ok = True
        logger.info("PDF chat: checkpointer ready")
    except Exception as exc:
        logger.warning("PDF chat init failed (non-fatal): %s", exc)

    # RAG 預熱（向量庫 + reranker），checkpointer 失敗仍執行
    rag_ok = False
    try:
        from app.rag import warmup as rag_warmup
        rag_ok = await rag_warmup()
    except Exception as exc:
        logger.warning("RAG warmup failed (non-fatal): %s", exc)

    _pdf_init_ready = pdf_ok
    _rag_init_ready = rag_ok

    yield

    _pdf_init_ready = False
    _rag_init_ready = False

    # PDF 問答 shutdown：先 drain 再等 tasks，最後關 pool
    try:
        from app.agents.pdf.research.agent import request_all_drain
        request_all_drain("server_shutdown")

        from app.agents.pdf.research import _background_tasks
        from app.agents.pdf.router_agent import _router_background_tasks
        pending = list(_background_tasks) + list(_router_background_tasks)
        if pending:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=10.0,
            )
    except asyncio.TimeoutError:
        logger.warning("PDF chat shutdown: background tasks did not finish within 10s")
    except Exception as exc:
        logger.warning("PDF chat shutdown error (non-fatal): %s", exc)
    finally:
        try:
            from app.agents.pdf.runner import shutdown_checkpointer
            await shutdown_checkpointer()
        except Exception as exc:
            logger.warning("PDF chat checkpointer shutdown failed: %s", exc)
        try:
            from app.rag import close_qdrant_clients
            await close_qdrant_clients()
        except Exception as exc:
            logger.warning("Qdrant client shutdown failed: %s", exc)
        try:
            from app.database_pdf import dispose_pdf_engine
            dispose_pdf_engine()
        except Exception as exc:
            logger.warning("PDF DB engine dispose failed: %s", exc)


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


@app.get("/ready")
async def readiness_check():
    if not (_pdf_init_ready and _rag_init_ready):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "pdf_chat": "ready" if _pdf_init_ready else "initializing",
                "rag": "ready" if _rag_init_ready else "initializing",
            },
        )
    return {
        "status": "ready",
        "pdf_chat": "ready",
        "rag": "ready",
    }
