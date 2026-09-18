from __future__ import annotations

import re
import unicodedata

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_SLUG = re.compile(r"[^a-z0-9-]+")


def sanitize_filename(name: str, max_len: int = 200) -> str:
    """Normalize a filename and strip anything that could be a path component."""
    name = unicodedata.normalize("NFKD", name)
    name = name.replace("\\", "/").split("/")[-1]  # drop any path prefix
    name = name.strip().lstrip(".")
    name = _SAFE_FILENAME.sub("_", name)
    if not name:
        name = "file"
    return name[:max_len]


def sanitize_slug(name: str, max_len: int = 64) -> str:
    """Turn a project name into a filesystem/URL-safe slug."""
    slug = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    slug = slug.strip().replace(" ", "-")
    slug = _SAFE_SLUG.sub("-", slug).strip("-")
    if not slug:
        slug = "project"
    return slug[:max_len]


ALLOWED_UPLOAD_EXTENSIONS = {".py", ".js", ".txt", ".json", ".zip", ".env", ".cfg", ".ini", ".toml"}


def is_allowed_upload(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in ALLOWED_UPLOAD_EXTENSIONS)
