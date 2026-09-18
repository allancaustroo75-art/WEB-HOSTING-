from __future__ import annotations

import os
import time
from typing import List, Optional

from fastapi import APIRouter, Cookie, File, Form, Header, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.api.auth import require_session
from backend.config import settings
from backend.database.db import Database
from backend.process.manager import ProcessManager
from backend.services.naming import is_allowed_upload, sanitize_filename, sanitize_slug
from backend.services.telegram_auth import is_owner_user


class FileWriteRequest(BaseModel):
    content: str


class RenameRequest(BaseModel):
    new_path: str


class CreateProjectRequest(BaseModel):
    name: str
    runtime: str = "python"
    description: str = ""


class CreateFileRequest(BaseModel):
    path: str
    content: str = ""
    is_dir: bool = False


class ProjectsAPI:
    def __init__(self, db: Database, pm: ProcessManager) -> None:
        self.db = db
        self.pm = pm

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/api", tags=["projects"])

        # ---- ME ---- (Updated to only show @username + photo per requirements)
        @router.get("/me")
        async def get_me(
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_session(bh_session, authorization, x_telegram_init_data)
            owner_id = session["owner_id"]
            projects = self.db.list_projects(owner_id)

            running = 0
            for p in projects:
                p["runtime_status"] = self.pm.status(p["id"])
                if p["runtime_status"] == "running":
                    running += 1

            total = len(projects)
            stopped = total - running

            tg_user = self.db.get_telegram_user(owner_id)

            recent = self.db.list_activity(limit=10, owner_id=owner_id)

            total_memory = 0
            for p in projects:
                if p["runtime_status"] == "running":
                    res = self.pm.get_resource_info(p["id"])
                    total_memory += res.get("memory", 0)

            username = session.get("tg_username") or (tg_user["username"] if tg_user else None)
            photo_url = session.get("tg_photo_url") or (tg_user["photo_url"] if tg_user else "")
            display_username = f"@{username}" if username else "@username_unavailable"

            is_owner = is_owner_user(owner_id, settings.owner_user_id, settings.admin_user_ids)

            return {
                "owner_id": owner_id,
                "username": username,
                "display_username": display_username,
                "photo_url": photo_url,
                "is_owner": is_owner,
                "stats": {
                    "total": total,
                    "running": running,
                    "stopped": stopped,
                    "memory_usage": total_memory,
                },
                "recent_activity": recent,
            }

        @router.get("/activity")
        async def get_activity(
            limit: int = 20,
            offset: int = 0,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_session(bh_session, authorization, x_telegram_init_data)
            owner_id = session["owner_id"]
            # If owner, can see all activity? For now, owner sees own, but global stats via admin
            if session.get("is_owner"):
                activity = self.db.list_activity(limit=limit, offset=offset, owner_id=None)
            else:
                activity = self.db.list_activity(limit=limit, offset=offset, owner_id=owner_id)
            return {"activity": activity}

        # ---- PROJECTS LIST ----
        @router.get("/projects")
        async def list_projects(
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_session(bh_session, authorization, x_telegram_init_data)
            owner_id = session["owner_id"]
            # Normal users only own projects, owner can see own via this endpoint
            # Global view via /api/admin/projects
            projects = self.db.list_projects(owner_id)
            for p in projects:
                p["runtime_status"] = self.pm.status(p["id"])
                p["runtime"] = p.get("runtime") or self.pm.detect_runtime(p["id"])
                p["resource"] = self.pm.get_resource_info(p["id"])
                p["created_date"] = p.get("created_at")
            return {"projects": projects}

        # ---- CREATE PROJECT ----
        @router.post("/projects")
        async def create_project(
            request: Request,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            session = require_session(bh_session, authorization, x_telegram_init_data)
            owner_id = session["owner_id"]

            content_type = request.headers.get("content-type", "")

            name = None
            runtime = "python"
            description = ""
            upload_file: UploadFile | None = None

            if "multipart/form-data" in content_type:
                form = await request.form()
                name = form.get("name")
                runtime = form.get("runtime", "python")
                description = form.get("description", "")
                if "file" in form:
                    upload_file = form["file"]
                elif "zip" in form:
                    upload_file = form["zip"]
            else:
                try:
                    body = await request.json()
                    name = body.get("name")
                    runtime = body.get("runtime", "python")
                    description = body.get("description", "")
                except Exception:
                    raise HTTPException(status_code=400, detail="Invalid request body")

            if not name or not name.strip():
                raise HTTPException(status_code=400, detail="Project name is required")
            name = name.strip()[:64]

            if runtime not in settings.supported_runtimes and runtime not in ["python", "node", "python+node"]:
                runtime = "python"

            if self.db.count_projects(owner_id) >= settings.max_projects_per_user:
                raise HTTPException(status_code=400, detail=f"Project limit reached ({settings.max_projects_per_user})")

            slug = sanitize_slug(f"{owner_id}-{name}-{int(time.time())}")
            project = self.db.create_project(owner_id, name, slug, runtime=runtime, description=description)
            project_id = project["id"]

            main_file = None

            if upload_file:
                filename = sanitize_filename(upload_file.filename or "upload.zip")
                if not is_allowed_upload(filename):
                    self.pm.delete(project_id)
                    self.db.delete_project(project_id)
                    raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")

                content = await upload_file.read()
                if len(content) > settings.max_upload_bytes:
                    self.pm.delete(project_id)
                    self.db.delete_project(project_id)
                    raise HTTPException(status_code=400, detail="File too large")

                try:
                    self.pm.save_upload(project_id, filename, content)
                except ValueError as exc:
                    self.pm.delete(project_id)
                    self.db.delete_project(project_id)
                    raise HTTPException(status_code=400, detail=str(exc))

                self.db.add_file(project_id, filename, len(content))

                if filename.endswith((".py", ".js")):
                    main_file = filename
                else:
                    candidates = [
                        f for f in self.pm.list_files(project_id)
                        if f.endswith(("main.py", "bot.py", "app.py", "index.js", "main.js", "bot.js", "server.js"))
                    ]
                    main_file = candidates[0] if candidates else None

                if not main_file:
                    all_files = self.pm.list_files(project_id)
                    py_files = [f for f in all_files if f.endswith(".py")]
                    js_files = [f for f in all_files if f.endswith(".js")]
                    if py_files:
                        main_file = py_files[0]
                    elif js_files:
                        main_file = js_files[0]

                self.pm.install_requirements(project_id)

            if main_file:
                self.db.update_project(project_id, main_file=main_file)

            self.db.add_activity("create_project", str(owner_id), project_id, name)

            project = self.db.get_project(project_id)
            project["runtime_status"] = self.pm.status(project_id)
            project["runtime"] = runtime
            return project

        # ---- GET SINGLE PROJECT ----
        @router.get("/projects/{project_id}")
        async def get_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            project = self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            project["runtime_status"] = self.pm.status(project_id)
            project["runtime"] = project.get("runtime") or self.pm.detect_runtime(project_id)
            project["files"] = self.pm.list_files(project_id)
            project["files_detailed"] = self.pm.list_files_detailed(project_id)
            project["resource"] = self.pm.get_resource_info(project_id)
            # Owner info for display (only username)
            owner = self.db.get_telegram_user(project["owner_id"])
            project["owner_username"] = owner["username"] if owner and owner.get("username") else None
            project["owner_display_username"] = f"@{project['owner_username']}" if project["owner_username"] else "@username_unavailable"
            return project

        # ---- START ----
        @router.post("/projects/{project_id}/start")
        async def start_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            project = self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            if not project["main_file"]:
                files = self.pm.list_files(project_id)
                candidates = [f for f in files if f.endswith(("main.py", "bot.py", "app.py", "index.js", "main.js"))]
                if candidates:
                    project["main_file"] = candidates[0]
                    self.db.update_project(project_id, main_file=candidates[0])
                else:
                    raise HTTPException(status_code=400, detail="No entrypoint found. Set main file or upload a valid bot file.")
            _, note = await self.pm.start(project_id, project["main_file"])
            self.db.update_project(project_id, status="running")
            self.db.add_activity("start", str(project["owner_id"]), project_id)
            return {"status": "running", "note": note, "resource": self.pm.get_resource_info(project_id)}

        # ---- STOP ----
        @router.post("/projects/{project_id}/stop")
        async def stop_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            project = self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            await self.pm.stop(project_id)
            self.db.update_project(project_id, status="stopped")
            self.db.add_activity("stop", str(project["owner_id"]), project_id)
            return {"status": "stopped"}

        # ---- RESTART ----
        @router.post("/projects/{project_id}/restart")
        async def restart_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            project = self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            if not project["main_file"]:
                raise HTTPException(status_code=400, detail="No entrypoint set for this project")
            _, note = await self.pm.restart(project_id, project["main_file"])
            self.db.update_project(project_id, status="running")
            self.db.add_activity("restart", str(project["owner_id"]), project_id)
            return {"status": "running", "note": note, "resource": self.pm.get_resource_info(project_id)}

        # ---- DELETE ----
        @router.delete("/projects/{project_id}")
        async def delete_project(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            project = self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            await self.pm.stop(project_id)
            self.db.add_activity("delete", str(project["owner_id"]), project_id, project["name"])
            self.pm.delete(project_id)
            self.db.delete_project(project_id)
            return {"ok": True}

        # ---- LOGS ----
        @router.get("/projects/{project_id}/logs")
        async def get_logs(
            project_id: int,
            lines: int = 200,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            lines = min(max(lines, 1), 1000)
            return {"lines": self.pm.tail(project_id, lines), "status": self.pm.status(project_id)}

        @router.delete("/projects/{project_id}/logs")
        async def clear_logs(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            self.pm.clear_logs(project_id)
            return {"ok": True}

        # ---- FILES LIST ----
        @router.get("/projects/{project_id}/files")
        async def list_files(
            project_id: int,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            files = self.pm.list_files_detailed(project_id)
            return {"files": files}

        # ---- FILE UPLOAD / CREATE ----
        @router.post("/projects/{project_id}/files")
        async def upload_or_create_file(
            project_id: int,
            request: Request,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            project = self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            content_type = request.headers.get("content-type", "")

            if "multipart/form-data" in content_type:
                form = await request.form()
                if "file" not in form:
                    raise HTTPException(status_code=400, detail="No file uploaded")
                upload_file = form["file"]
                path = form.get("path") or upload_file.filename
                content = await upload_file.read()

                if len(content) > settings.max_upload_bytes:
                    raise HTTPException(status_code=400, detail="File too large")

                target_path = path or upload_file.filename
                try:
                    self.pm.write_file(project_id, target_path, content.decode(errors="replace") if isinstance(content, bytes) else content)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid path")

                self.db.add_file(project_id, target_path, len(content))
                self.db.add_activity("upload_file", str(project["owner_id"]), project_id, target_path)
                return {"ok": True, "path": target_path, "size": len(content)}

            else:
                try:
                    body = await request.json()
                except Exception:
                    raise HTTPException(status_code=400, detail="Invalid JSON")

                path = body.get("path")
                content = body.get("content", "")
                if not path:
                    raise HTTPException(status_code=400, detail="Path is required")

                try:
                    self.pm.write_file(project_id, path, content)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid path")

                self.db.add_file(project_id, path, len(content.encode()))
                self.db.add_activity("create_file", str(project["owner_id"]), project_id, path)
                return {"ok": True, "path": path}

        # ---- READ FILE ----
        @router.get("/projects/{project_id}/files/{path:path}")
        async def read_file(
            project_id: int,
            path: str,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            try:
                content = self.pm.read_file(project_id, path)
                info = self.pm.get_file_info(project_id, path)
                ext = info["extension"] if info else ""
                language = "python" if ext == ".py" else "javascript" if ext in [".js", ".jsx", ".ts", ".tsx"] else ext.lstrip(".") or "text"
                return {"path": path, "content": content, "info": info, "language": language}
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid path")
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="File not found")

        # ---- WRITE FILE ----
        @router.put("/projects/{project_id}/files/{path:path}")
        async def write_file(
            project_id: int,
            path: str,
            body: FileWriteRequest,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            project = self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            try:
                self.pm.write_file(project_id, path, body.content)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid path")
            self.db.add_activity("edit_file", str(project["owner_id"]), project_id, path)
            return {"ok": True}

        # ---- RENAME FILE ----
        @router.post("/projects/{project_id}/files/{path:path}/rename")
        async def rename_file(
            project_id: int,
            path: str,
            body: RenameRequest,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            project = self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            if not body.new_path or not body.new_path.strip():
                raise HTTPException(status_code=400, detail="New path required")
            try:
                self.pm.rename_file(project_id, path, body.new_path.strip())
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Source file not found")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            self.db.add_activity("rename_file", str(project["owner_id"]), project_id, f"{path} -> {body.new_path}")
            return {"ok": True, "old_path": path, "new_path": body.new_path}

        # ---- DELETE FILE ----
        @router.delete("/projects/{project_id}/files/{path:path}")
        async def delete_file(
            project_id: int,
            path: str,
            bh_session: str | None = Cookie(default=None),
            authorization: str | None = Header(default=None),
            x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        ):
            project = self._owned_project(project_id, bh_session, authorization, x_telegram_init_data)
            try:
                ok = self.pm.delete_file(project_id, path)
                if not ok:
                    raise HTTPException(status_code=404, detail="File not found")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid path")
            self.db.add_activity("delete_file", str(project["owner_id"]), project_id, path)
            return {"ok": True}

        return router

    def _owned_project(self, project_id: int, cookie_value: str | None, authorization: str | None = None, x_telegram_init_data: str | None = None) -> dict:
        """
        Ownership check with owner override:
        - Normal users: only own projects
        - Owner/Admin: can access any project
        Server-side check, never trust client
        """
        session = require_session(cookie_value, authorization, x_telegram_init_data)
        project = self.db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Owner can access all
        if session.get("is_owner"):
            return project

        # Normal user only own
        if project["owner_id"] != session["owner_id"]:
            raise HTTPException(status_code=404, detail="Project not found")

        return project
