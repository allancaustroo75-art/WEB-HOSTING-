"""
SNUKED HOSTER - Single Configuration File
No .env file required. Edit values below directly.
Railway compatibility: If environment variables are set (by Railway), they will override these values.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

# =============================================================================
# DEPLOYMENT CONFIGURATION - EDIT THESE VALUES
# =============================================================================

# Telegram Bot Token from @BotFather
BOT_TOKEN = "8521376955:AAHlP7ZuZXSkIJbDS_bVUUx8Lg6zpstBH3s"

# Owner Telegram User ID (numeric) - has full global access to all projects
OWNER_USER_ID = 7743406267

# Additional admin user IDs (optional)
ADMIN_USER_IDS = []  # e.g. [123456789, 987654321]

# Secret key for session signing - generate a random string (at least 32 chars)
# You can generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = "SNUKED"

# Public URL where Mini App is hosted (Railway domain)
MINI_APP_URL = "https://YOUR-RAILWAY-DOMAIN"

# CORS Origins - allowed frontend origins
CORS_ORIGINS = ["https://YOUR-RAILWAY-DOMAIN"]

# Persistent storage paths (keep these for Railway volume compatibility)
DATABASE_PATH = "./data/bothost.db"
PROJECTS_DIR = "./projects"

# =============================================================================
# ADVANCED SETTINGS (optional, sensible defaults)
# =============================================================================

HOST = "0.0.0.0"
PORT = 8000
COOKIE_SECURE = False
MAX_PROJECTS_PER_USER = 10
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
PROCESS_CPU_SECONDS = 3600
PROCESS_MEMORY_MB = 256
LOGIN_TOKEN_TTL_SECONDS = 900  # 15 min
SESSION_TTL_SECONDS = 12 * 3600  # 12 hours
SUPPORTED_RUNTIMES = ["python", "node", "python+node"]

# =============================================================================
# INTERNAL - Settings dataclass that reads from above constants
# Allows Railway env vars to override if present (for compatibility)
# =============================================================================

def _get_env(name: str, default):
    """Get from OS env if set (Railway), else use config constant"""
    return os.getenv(name, default)

def _get_env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default

def _get_env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

def _get_env_list(name: str, default: list) -> list:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return [x.strip() for x in v.split(",") if x.strip()]

@dataclass
class Settings:
    # Core - from constants above, with env override for Railway
    bot_token: str = field(default_factory=lambda: _get_env("BOT_TOKEN", BOT_TOKEN))
    owner_user_id: int = field(default_factory=lambda: _get_env_int("OWNER_USER_ID", OWNER_USER_ID))
    admin_user_ids: set[int] = field(default_factory=lambda: {
        int(x) for x in (_get_env_list("ADMIN_USER_IDS", [str(i) for i in ADMIN_USER_IDS]) ) if str(x).isdigit()
    })
    secret_key: str = field(default_factory=lambda: _get_env("SECRET_KEY", SECRET_KEY))
    database_path: str = field(default_factory=lambda: _get_env("DATABASE_PATH", DATABASE_PATH))
    projects_dir: Path = field(default_factory=lambda: Path(_get_env("PROJECTS_DIR", PROJECTS_DIR)).resolve())

    # URLs
    mini_app_url: str = field(default_factory=lambda: _get_env("MINI_APP_URL", _get_env("DASHBOARD_BASE_URL", MINI_APP_URL)))
    dashboard_base_url: str = field(default_factory=lambda: _get_env("DASHBOARD_BASE_URL", _get_env("MINI_APP_URL", MINI_APP_URL)))

    # Security / limits
    login_token_ttl_seconds: int = field(default_factory=lambda: _get_env_int("LOGIN_TOKEN_TTL_SECONDS", LOGIN_TOKEN_TTL_SECONDS))
    session_ttl_seconds: int = field(default_factory=lambda: _get_env_int("SESSION_TTL_SECONDS", SESSION_TTL_SECONDS))
    max_projects_per_user: int = field(default_factory=lambda: _get_env_int("MAX_PROJECTS_PER_USER", MAX_PROJECTS_PER_USER))
    max_upload_bytes: int = field(default_factory=lambda: _get_env_int("MAX_UPLOAD_BYTES", MAX_UPLOAD_BYTES))
    process_cpu_seconds: int = field(default_factory=lambda: _get_env_int("PROCESS_CPU_SECONDS", PROCESS_CPU_SECONDS))
    process_memory_mb: int = field(default_factory=lambda: _get_env_int("PROCESS_MEMORY_MB", PROCESS_MEMORY_MB))
    cors_origins: list[str] = field(default_factory=lambda: _get_env_list("CORS_ORIGINS", CORS_ORIGINS) or ["*"])
    cookie_secure: bool = field(default_factory=lambda: _get_env_bool("COOKIE_SECURE", COOKIE_SECURE))
    host: str = field(default_factory=lambda: _get_env("HOST", HOST))
    port: int = field(default_factory=lambda: _get_env_int("PORT", PORT))
    supported_runtimes: list[str] = field(default_factory=lambda: SUPPORTED_RUNTIMES)


settings = Settings()

# Ensure persistent directories exist (Railway volume compatibility)
settings.projects_dir.mkdir(parents=True, exist_ok=True)
Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)

# Auto-generate secret key warning if still placeholder
if settings.secret_key in ("GENERATE_A_RANDOM_SECRET_HERE", "change-me-in-production", "", "PASTE_BOT_TOKEN_HERE"):
    # Generate a temporary one for dev, but warn
    # In production, user should set a proper secret
    if settings.secret_key == "GENERATE_A_RANDOM_SECRET_HERE":
        # Keep as is for user to edit, but create a runtime random for safety if not set
        pass
