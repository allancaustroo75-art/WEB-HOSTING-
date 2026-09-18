from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import BaseModel

from backend.api.auth import require_owner
from backend.config import settings
from backend.database.db import Database
from backend.process.manager import ProcessManager
from backend.services.naming import sanitize_filename


class FileWriteRequest(BaseModel):
    content: str


class RenameRequest(BaseModel):
    new_path: str


class CreateFileRequest(BaseModel):
    path: str
    content: str = ""


class AdminAPI:
    def __init__(self, db: Database, pm: ProcessManager) -> None:
        self.db = db
        self.pm = pm

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/api/admin", tags=["admin"])

        # ---- STATS ----
        @router.get("/stats")
        async def get_stats(
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            require_owner(bh_session, authorization, x_telegram_init_data)
            stats = self.db.get_global_stats()
            # Enrich with live running count from ProcessManager
            all_projects = self.db.list_all_projects()
            running = 0
            for p in all_projects:
                if self.pm.status(p["id"]) == "running":
                    running += 1
            stats["running_projects"] = running
            stats["stopped_projects"] = stats["total_projects"] - running
            return stats

        # ---- USERS ----
        @router.get("/users")
        async def list_users(
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            require_owner(bh_session, authorization, x_telegram_init_data)
            users = self.db.list_all_users_with_stats()
            # Only expose username + photo_url per requirements, not first_name/last_name
            # Also provide fallback for username
            result = []
            for u in users:
                username = u.get("username")
                display_username = f"@{username}" if username else "@username_unavailable"
                result.append({
                    "user_id": u["user_id"],  # internal ID needed for API but UI should not display numeric ID as profile
                    "username": username,
                    "display_username": display_username,
                    "photo_url": u.get("photo_url", ""),
                    "total_projects": u.get("total_projects", 0),
                    "running_projects": u.get("running_projects", 0),
                    "last_seen": u.get("last_seen", 0),
                })
            return {"users": result}

        @router.get("/users/{user_id}/projects")
        async def list_user_projects(
            user_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            require_owner(bh_session, authorization, x_telegram_init_data)
            projects = self.db.list_projects_by_user(user_id)
            for p in projects:
                p["runtime_status"] = self.pm.status(p["id"])
                p["runtime"] = p.get("runtime") or self.pm.detect_runtime(p["id"])
                p["resource"] = self.pm.get_resource_info(p["id"])
            # Get user info for display
            tg_user = self.db.get_telegram_user(user_id)
            username = tg_user["username"] if tg_user and tg_user.get("username") else None
            display_username = f"@{username}" if username else "@username_unavailable"
            return {
                "user_id": user_id,
                "username": username,
                "display_username": display_username,
                "photo_url": tg_user["photo_url"] if tg_user else "",
                "projects": projects,
            }

        # ---- ALL PROJECTS ----
        @router.get("/projects")
        async def list_all_projects(
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            require_owner(bh_session, authorization, x_telegram_init_data)
            projects = self.db.list_all_projects()
            for p in projects:
                p["runtime_status"] = self.pm.status(p["id"])
                p["runtime"] = p.get("runtime") or self.pm.detect_runtime(p["id"])
                p["resource"] = self.pm.get_resource_info(p["id"])
                # Attach owner username for display
                owner = self.db.get_telegram_user(p["owner_id"])
                p["owner_username"] = owner["username"] if owner and owner.get("username") else None
                p["owner_display_username"] = f"@{p['owner_username']}" if p["owner_username"] else "@username_unavailable"
            return {"projects": projects}

        # ---- SINGLE PROJECT (OWNER ACCESS) ----
        @router.get("/projects/{project_id}")
        async def get_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            project["runtime_status"] = self.pm.status(project_id)
            project["runtime"] = project.get("runtime") or self.pm.detect_runtime(project_id)
            project["files"] = self.pm.list_files(project_id)
            project["files_detailed"] = self.pm.list_files_detailed(project_id)
            project["resource"] = self.pm.get_resource_info(project_id)
            owner = self.db.get_telegram_user(project["owner_id"])
            project["owner_username"] = owner["username"] if owner and owner.get("username") else None
            project["owner_display_username"] = f"@{project['owner_username']}" if project["owner_username"] else "@username_unavailable"
            project["owner_photo_url"] = owner["photo_url"] if owner else ""
            return project

        @router.delete("/projects/{project_id}")
        async def delete_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            await self.pm.stop(project_id)
            self.db.add_activity("admin_delete", str(session["owner_id"]), project_id, f"owner deleted {project['name']} owned by {project['owner_id']}")
            self.pm.delete(project_id)
            self.db.delete_project(project_id)
            return {"ok": True}

        # ---- CONTROLS ----
        @router.post("/projects/{project_id}/start")
        async def start_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            if not project["main_file"]:
                files = self.pm.list_files(project_id)
                candidates = [f for f in files if f.endswith(("main.py", "bot.py", "app.py", "index.js", "main.js"))]
                if candidates:
                    project["main_file"] = candidates[0]
                    self.db.update_project(project_id, main_file=candidates[0])
                else:
                    raise HTTPException(status_code=400, detail="No entrypoint found")
            _, note = await self.pm.start(project_id, project["main_file"])
            self.db.update_project(project_id, status="running")
            self.db.add_activity("admin_start", str(session["owner_id"]), project_id)
            return {"status": "running", "note": note, "resource": self.pm.get_resource_info(project_id)}

        @router.post("/projects/{project_id}/stop")
        async def stop_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            await self.pm.stop(project_id)
            self.db.update_project(project_id, status="stopped")
            self.db.add_activity("admin_stop", str(session["owner_id"]), project_id)
            return {"status": "stopped"}

        @router.post("/projects/{project_id}/restart")
        async def restart_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            if not project["main_file"]:
                raise HTTPException(status_code=400, detail="No entrypoint set")
            _, note = await self.pm.restart(project_id, project["main_file"])
            self.db.update_project(project_id, status="running")
            self.db.add_activity("admin_restart", str(session["owner_id"]), project_id)
            return {"status": "running", "note": note, "resource": self.pm.get_resource_info(project_id)}

        # ---- FILES ----
        @router.get("/projects/{project_id}/files")
        async def list_files(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            files = self.pm.list_files_detailed(project_id)
            return {"files": files}

        @router.get("/projects/{project_id}/files/{path:path}")
        async def read_file(
            project_id: int,
            path: str,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            try:
                content = self.pm.read_file(project_id, path)
                info = self.pm.get_file_info(project_id, path)
                # Add language detection
                ext = info["extension"] if info else ""
                language = "python" if ext == ".py" else "javascript" if ext in [".js", ".jsx", ".ts", ".tsx"] else ext.lstrip(".") or "text"
                return {"path": path, "content": content, "info": info, "language": language}
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid path")
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="File not found")

        @router.put("/projects/{project_id}/files/{path:path}")
        async def write_file(
            project_id: int,
            path: str,
            body: FileWriteRequest,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            try:
                self.pm.write_file(project_id, path, body.content)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid path")
            self.db.add_activity("admin_edit_file", str(session["owner_id"]), project_id, path)
            return {"ok": True}

        @router.post("/projects/{project_id}/files")
        async def create_or_upload_file(
            project_id: int,
            request: Request,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            content_type = request.headers.get("content-type", "")
            if "multipart/form-data" in content_type:
                form = await request.form()
                if "file" not in form:
                    raise HTTPException(status_code=400, detail="No file uploaded")
                upload_file = form["file"]
                path = form.get("path") or upload_file.filename
                content = await upload_file.read()
                try:
                    self.pm.write_file(project_id, path, content.decode(errors="replace") if isinstance(content, bytes) else content)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid path")
                self.db.add_activity("admin_upload_file", str(session["owner_id"]), project_id, path)
                return {"ok": True, "path": path}
            else:
                try:
                    body = await request.json()
                except Exception:
                    raise HTTPException(status_code=400, detail="Invalid JSON")
                path = body.get("path")
                content = body.get("content", "")
                if not path:
                    raise HTTPException(status_code=400, detail="Path required")
                try:
                    self.pm.write_file(project_id, path, content)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid path")
                self.db.add_activity("admin_create_file", str(session["owner_id"]), project_id, path)
                return {"ok": True, "path": path}

        @router.delete("/projects/{project_id}/files/{path:path}")
        async def delete_file(
            project_id: int,
            path: str,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            try:
                ok = self.pm.delete_file(project_id, path)
                if not ok:
                    raise HTTPException(status_code=404, detail="File not found")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid path")
            self.db.add_activity("admin_delete_file", str(session["owner_id"]), project_id, path)
            return {"ok": True}

        @router.post("/projects/{project_id}/files/{path:path}/rename")
        async def rename_file(
            project_id: int,
            path: str,
            body: RenameRequest,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            if not body.new_path or not body.new_path.strip():
                raise HTTPException(status_code=400, detail="New path required")
            try:
                self.pm.rename_file(project_id, path, body.new_path.strip())
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Source file not found")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            self.db.add_activity("admin_rename_file", str(session["owner_id"]), project_id, f"{path} -> {body.new_path}")
            return {"ok": True, "old_path": path, "new_path": body.new_path}

        @router.get("/projects/{project_id}/logs")
        async def get_logs(
            project_id: int,
            lines: int = 200,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            lines = min(max(lines, 1), 1000)
            return {"lines": self.pm.tail(project_id, lines), "status": self.pm.status(project_id)}

        @router.delete("/projects/{project_id}/logs")
        async def clear_logs(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            require_owner(bh_session, authorization, x_telegram_init_data)
            project = self.db.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            self.pm.clear_logs(project_id)
            return {"ok": True}

        return router
