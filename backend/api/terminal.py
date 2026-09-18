from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from backend.config import settings
from backend.database.db import Database
from backend.process.manager import ProcessManager
from backend.services.security import verify_session
from backend.services.telegram_auth import validate_telegram_init_data, is_owner_user

log = logging.getLogger(__name__)


class TerminalAPI:
    def __init__(self, db: Database, pm: ProcessManager) -> None:
        self.db = db
        self.pm = pm

    def router(self) -> APIRouter:
        router = APIRouter(tags=["terminal"])

        @router.websocket("/ws/projects/{project_id}/logs")
        async def logs_ws(websocket: WebSocket, project_id: int, initData: Optional[str] = Query(default=None)):
            authenticated = False
            owner_id = None
            is_owner = False

            cookie_value = websocket.cookies.get("bh_session")
            session = verify_session(cookie_value, settings.secret_key) if cookie_value else None

            if session:
                owner_id = session.get("owner_id")
                is_owner = session.get("is_owner") or is_owner_user(
                    owner_id, settings.owner_user_id, settings.admin_user_ids
                )
                project = self.db.get_project(project_id)
                if project and (project["owner_id"] == owner_id or is_owner):
                    authenticated = True

            if not authenticated and initData and settings.bot_token:
                validated = validate_telegram_init_data(initData, settings.bot_token)
                if validated:
                    owner_id = validated["user_id"]
                    is_owner = is_owner_user(owner_id, settings.owner_user_id, settings.admin_user_ids)
                    project = self.db.get_project(project_id)
                    if project and (project["owner_id"] == owner_id or is_owner):
                        authenticated = True

            if not authenticated:
                await websocket.close(code=4401)
                return

            await websocket.accept()
            sent = 0
            try:
                while True:
                    lines = self.pm.tail(project_id, 1000)
                    if len(lines) > sent:
                        for line in lines[sent:]:
                            await websocket.send_text(line)
                        sent = len(lines)
                    await asyncio.sleep(1)
            except WebSocketDisconnect:
                return
            except Exception as e:
                log.warning(f"WS error: {e}")
                try:
                    await websocket.close()
                except Exception:
                    pass

        return router
