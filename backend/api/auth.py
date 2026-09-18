from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from pydantic import BaseModel

from backend.config import settings
from backend.database.db import Database
from backend.services.security import generate_csrf_token, sign_session, verify_session
from backend.services.telegram_auth import extract_init_data_from_header, validate_telegram_init_data, is_owner_user

SESSION_COOKIE = "bh_session"


class TokenLoginRequest(BaseModel):
    token: str


class TelegramAuthRequest(BaseModel):
    initData: str


def _check_owner(user_id: int) -> bool:
    """Server-side owner check - never trust client"""
    return is_owner_user(user_id, settings.owner_user_id, settings.admin_user_ids)


class AuthAPI:
    def __init__(self, db: Database) -> None:
        self.db = db

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/api/auth", tags=["auth"])

        @router.post("/token-login")
        async def token_login(body: TokenLoginRequest, response: Response):
            owner_id = self.db.consume_login_token(body.token)
            if owner_id is None:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            csrf = generate_csrf_token()
            is_owner = _check_owner(owner_id)
            session = sign_session(
                {"owner_id": owner_id, "csrf": csrf, "is_owner": is_owner},
                settings.secret_key,
                settings.session_ttl_seconds,
            )
            response.set_cookie(
                SESSION_COOKIE,
                session,
                httponly=True,
                samesite="lax",
                secure=settings.cookie_secure,
                max_age=settings.session_ttl_seconds,
            )
            self.db.add_activity("login", str(owner_id))
            return {"ok": True, "owner_id": owner_id, "csrf_token": csrf, "is_owner": is_owner}

        @router.post("/telegram")
        async def telegram_auth(body: TelegramAuthRequest, response: Response, request: Request):
            """
            Validates Telegram Mini App initData and creates a secure session.
            Primary auth for Mini App.
            """
            if not settings.bot_token:
                raise HTTPException(status_code=500, detail="Bot token not configured")

            validated = validate_telegram_init_data(body.initData, settings.bot_token)
            if not validated:
                raise HTTPException(status_code=401, detail="Invalid Telegram initData")

            user_id = validated.get("user_id")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid Telegram user")

            self.db.record_active_user(user_id)

            # Store telegram profile - only username and photo_url are displayed in UI per requirements
            # First name stored internally but not displayed
            try:
                self.db.upsert_telegram_user(
                    user_id,
                    username=validated.get("username"),
                    first_name=validated.get("first_name"),
                    last_name=validated.get("last_name"),
                    language_code=validated.get("language_code"),
                    is_premium=validated.get("is_premium", False),
                    photo_url=validated.get("photo_url", ""),
                )
            except Exception:
                pass

            csrf = generate_csrf_token()
            is_owner = _check_owner(user_id)
            session_payload = {
                "owner_id": user_id,
                "csrf": csrf,
                "tg_username": validated.get("username"),
                "tg_photo_url": validated.get("photo_url", ""),
                "is_owner": is_owner,
            }
            session = sign_session(session_payload, settings.secret_key, settings.session_ttl_seconds)
            response.set_cookie(
                SESSION_COOKIE,
                session,
                httponly=True,
                samesite="lax",
                secure=settings.cookie_secure,
                max_age=settings.session_ttl_seconds,
            )

            self.db.add_activity("telegram_login", str(user_id))

            return {
                "ok": True,
                "owner_id": user_id,
                "csrf_token": csrf,
                "is_owner": is_owner,
                "username": validated.get("username"),
                "photo_url": validated.get("photo_url", ""),
                "user": validated.get("user"),
            }

        @router.get("/me")
        async def me(
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            """
            Returns current authenticated user.
            Only exposes @username and photo, not first_name per requirements.
            """
            session = None
            tg_data = None

            init_data = extract_init_data_from_header(authorization, x_telegram_init_data)
            if init_data and settings.bot_token:
                validated = validate_telegram_init_data(init_data, settings.bot_token)
                if validated:
                    tg_data = validated
                    is_owner = _check_owner(validated["user_id"])
                    session = {
                        "owner_id": validated["user_id"],
                        "tg_username": validated.get("username"),
                        "tg_photo_url": validated.get("photo_url", ""),
                        "is_owner": is_owner,
                    }
                    # Update stored profile
                    try:
                        self.db.upsert_telegram_user(
                            validated["user_id"],
                            username=validated.get("username"),
                            first_name=validated.get("first_name"),
                            last_name=validated.get("last_name"),
                            language_code=validated.get("language_code"),
                            is_premium=validated.get("is_premium", False),
                            photo_url=validated.get("photo_url", ""),
                        )
                    except Exception:
                        pass

            if not session:
                session = self._require_session(bh_session)

            owner_id = session["owner_id"]
            tg_user = self.db.get_telegram_user(owner_id)

            # Determine is_owner server-side
            is_owner = _check_owner(owner_id)

            # Only expose username and photo_url per requirements
            username = session.get("tg_username") or (tg_user["username"] if tg_user else None)
            photo_url = session.get("tg_photo_url") or (tg_user["photo_url"] if tg_user else "")

            # Fallback for username
            display_username = f"@{username}" if username else "@username_unavailable"

            return {
                "owner_id": owner_id,  # internal, not displayed in UI per spec but needed for logic
                "username": username,
                "display_username": display_username,
                "photo_url": photo_url,
                "is_owner": is_owner,
                "is_admin": is_owner,
                # Stats for profile page
                "telegram_user": {
                    "username": username,
                    "photo_url": photo_url,
                } if tg_user else None,
            }

        @router.post("/logout")
        async def logout(response: Response):
            response.delete_cookie(SESSION_COOKIE)
            return {"ok": True}

        return router

    def _require_session(self, cookie_value: str | None) -> dict:
        if not cookie_value:
            raise HTTPException(status_code=401, detail="Not authenticated")
        session = verify_session(cookie_value, settings.secret_key)
        if session is None:
            raise HTTPException(status_code=401, detail="Session expired")
        # Re-evaluate is_owner server-side
        owner_id = session.get("owner_id")
        if owner_id:
            session["is_owner"] = _check_owner(owner_id)
        return session


def require_session(
    cookie_value: str | None = None,
    authorization: str | None = None,
    x_telegram_init_data: str | None = None,
) -> dict:
    """
    Shared helper other routers use to authenticate a request.
    Supports:
    - Cookie session (bh_session)
    - Authorization: tma <initData> with live validation
    - X-Telegram-Init-Data header
    Returns session dict with owner_id and is_owner (server-side checked)
    """
    # Try initData headers first for Mini App
    init_data = extract_init_data_from_header(authorization, x_telegram_init_data)
    if init_data and settings.bot_token:
        validated = validate_telegram_init_data(init_data, settings.bot_token)
        if validated:
            user_id = validated["user_id"]
            is_owner = is_owner_user(user_id, settings.owner_user_id, settings.admin_user_ids)
            return {
                "owner_id": user_id,
                "tg_username": validated.get("username"),
                "tg_photo_url": validated.get("photo_url", ""),
                "tg_user": validated.get("user"),
                "is_owner": is_owner,
                "auth_method": "telegram_init_data",
            }

    # Fallback to cookie session
    if not cookie_value:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = verify_session(cookie_value, settings.secret_key)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired")
    # Server-side owner check
    owner_id = session.get("owner_id")
    if owner_id:
        session["is_owner"] = is_owner_user(owner_id, settings.owner_user_id, settings.admin_user_ids)
    return session


def require_owner(
    cookie_value: str | None = None,
    authorization: str | None = None,
    x_telegram_init_data: str | None = None,
) -> dict:
    """
    Requires owner/admin privileges - server side check
    """
    session = require_session(cookie_value, authorization, x_telegram_init_data)
    if not session.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner access required")
    return session
