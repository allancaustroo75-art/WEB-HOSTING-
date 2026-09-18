from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.auth import AuthAPI
from backend.api.projects import ProjectsAPI
from backend.api.terminal import TerminalAPI
from backend.api.admin import AdminAPI
from backend.bot.runner import BotRunner
from backend.config import settings
from backend.database.db import Database
from backend.process.manager import ProcessManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

db = Database(settings.database_path)
pm = ProcessManager(settings.projects_dir, settings.process_cpu_seconds, settings.process_memory_mb)
bot_runner = BotRunner(db, pm, settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    try:
        await bot_runner.start()
    except Exception:
        log.exception("Telegram bot failed to start; API will remain available without it")
    yield
    await bot_runner.stop()


app = FastAPI(title="SNUKED HOSTER - Telegram Mini App Hosting", version="2.0.0", lifespan=lifespan)

# CORS: Secure configuration
# Allow Mini App origins + configured CORS_ORIGINS
allowed_origins = settings.cors_origins
# If wildcard, allow all but handle credentials carefully
# For production, CORS_ORIGINS should be set to exact Mini App URL and backend URL

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if "*" not in allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],  # Allow all headers including X-Telegram-Init-Data, Authorization
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "ALLOWALL")  # Allow iframe for Telegram WebView
    # Content Security Policy allowing Telegram
    # response.headers.setdefault("Content-Security-Policy", "frame-ancestors https://web.telegram.org https://*.telegram.org self")
    return response


# API Routers
app.include_router(AuthAPI(db).router())
app.include_router(ProjectsAPI(db, pm).router())
app.include_router(TerminalAPI(db, pm).router())
app.include_router(AdminAPI(db, pm).router())


@app.get("/health", tags=["system"])
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "telegram_configured": bot_runner.configured, "version": "2.0.0-miniapp"}


@app.get("/api/health", tags=["system"])
async def api_health():
    return {"status": "ok", "telegram_configured": bot_runner.configured}


@app.get("/api/runtimes", tags=["system"])
async def get_runtimes():
    return {"runtimes": settings.supported_runtimes}


# Frontend serving - Telegram Mini App
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    # Mount static assets
    css_dir = frontend_dir / "css"
    js_dir = frontend_dir / "js"
    assets_dir = frontend_dir / "assets"

    if css_dir.exists():
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if js_dir.exists():
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        # Serve Mini App index.html
        index_path = frontend_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return JSONResponse({"message": "SNUKED HOSTER Mini App - Frontend not built yet"})

    @app.get("/login.html", include_in_schema=False)
    async def legacy_login() -> FileResponse:
        # Keep legacy login for backward compat, but redirect to Mini App index
        login_path = frontend_dir / "login.html"
        if login_path.exists():
            return FileResponse(login_path)
        return FileResponse(frontend_dir / "index.html")

    @app.get("/dashboard.html", include_in_schema=False)
    async def legacy_dashboard() -> FileResponse:
        # Redirect legacy dashboard to new Mini App
        return FileResponse(frontend_dir / "index.html")

    @app.get("/projects.html", include_in_schema=False)
    async def legacy_projects() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

    @app.get("/project.html", include_in_schema=False)
    async def legacy_project() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

    # Catch-all for SPA routing - serve index.html for any non-API route
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        # Check if file exists in frontend dir
        target = frontend_dir / full_path
        if target.exists() and target.is_file():
            return FileResponse(target)
        # Otherwise serve index.html for SPA
        index_path = frontend_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return JSONResponse({"detail": "Not found"}, status_code=404)
