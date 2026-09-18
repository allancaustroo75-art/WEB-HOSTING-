from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def sign_session(payload: dict[str, Any], secret_key: str, ttl_seconds: int) -> str:
    body = dict(payload)
    body["exp"] = time.time() + ttl_seconds
    raw = json.dumps(body, separators=(",", ":")).encode()
    sig = hmac.new(secret_key.encode(), raw, hashlib.sha256).digest()
    return f"{_b64e(raw)}.{_b64e(sig)}"


def verify_session(token: str, secret_key: str) -> dict[str, Any] | None:
    try:
        raw_b64, sig_b64 = token.split(".", 1)
        raw = _b64d(raw_b64)
        sig = _b64d(sig_b64)
    except Exception:
        return None
    expected = hmac.new(secret_key.encode(), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    body = json.loads(raw)
    if body.get("exp", 0) < time.time():
        return None
    return body


def generate_csrf_token() -> str:
    import uuid

    return uuid.uuid4().hex
