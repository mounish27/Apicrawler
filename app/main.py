from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Playwright spawns subprocesses — ProactorEventLoop is required on Windows.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes import crawl

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="API Doc Intelligence Engine",
    description=(
        "Enterprise-grade API documentation crawler that converts any API docs "
        "to OpenAPI 3.1, Swagger 2.0, and Postman collections."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# API routes
app.include_router(crawl.router, tags=["crawl"])

# Serve frontend — must be registered AFTER API routes
@app.get("/", include_in_schema=False)
async def serve_ui():
    return FileResponse(str(_FRONTEND_DIR / "index.html"))

if _FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")
