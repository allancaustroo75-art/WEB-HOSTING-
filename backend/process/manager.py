from __future__ import annotations

import asyncio
import logging
import os
import re
import resource
import shutil
import subprocess
import sys
import zipfile
from collections import deque
from pathlib import Path
from typing import Deque, List, Dict, Any
import time

log = logging.getLogger(__name__)

MAX_LOG_LINES = 1000

# Import-name -> actual PyPI package name, for auto-installing on ModuleNotFoundError.
MODULE_PACKAGE_MAP = {
    "telebot": "pyTelegramBotAPI",
    "telegram": "python-telegram-bot",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "PIL": "Pillow",
    "sqlalchemy": "SQLAlchemy",
    "dateutil": "python-dateutil",
}

MISSING_MODULE_RE = re.compile(r"ModuleNotFoundError: No module named ['\"]([\w\.]+)['\"]")


class ManagedProject:
    """Runtime state for a single hosted project (in-memory, not persisted)."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.process: asyncio.subprocess.Process | None = None
        self.log_lines: Deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._reader_task: asyncio.Task | None = None
        self.started_at: float | None = None
        self.restart_count: int = 0

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.returncode is None


def _preexec_limits(cpu_seconds: int, memory_mb: int):
    """Applied in the child process before exec — best-effort resource caps (Linux only)."""

    def _limit() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            mem_bytes = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            # Detach from the parent's process group so a stop() can signal the whole tree.
            os.setsid()
        except Exception:
            pass

    return _limit


class ProcessManager:
    """Manages per-project virtualenvs and the (single) running process for each."""

    def __init__(self, projects_dir: Path, cpu_seconds: int, memory_mb: int) -> None:
        self.projects_dir = projects_dir
        self.cpu_seconds = cpu_seconds
        self.memory_mb = memory_mb
        self._runtime: dict[int, ManagedProject] = {}

    def project_dir(self, project_id: int) -> Path:
        d = self.projects_dir / str(project_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def venv_python(self, project_id: int) -> Path:
        return self.project_dir(project_id) / ".venv" / "bin" / "python"

    def save_upload(self, project_id: int, filename: str, content: bytes) -> Path:
        dest = self.project_dir(project_id) / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        if filename.lower().endswith(".zip"):
            self._extract_zip(dest)
        return dest

    def _extract_zip(self, zip_path: Path) -> None:
        target = zip_path.parent.resolve()
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                member_path = (target / member.filename).resolve()
                if not str(member_path).startswith(str(target)):
                    raise ValueError(f"Unsafe zip member (path traversal): {member.filename}")
            zf.extractall(target)
        zip_path.unlink(missing_ok=True)

    def list_files(self, project_id: int) -> list[str]:
        d = self.project_dir(project_id)
        return sorted(
            str(p.relative_to(d)) for p in d.rglob("*") if p.is_file() and ".venv" not in p.parts
        )

    def list_files_detailed(self, project_id: int) -> List[Dict[str, Any]]:
        """List files with metadata: size, extension, modified time"""
        d = self.project_dir(project_id)
        result = []
        for p in d.rglob("*"):
            if p.is_file() and ".venv" not in p.parts:
                rel = str(p.relative_to(d))
                try:
                    stat = p.stat()
                    result.append({
                        "path": rel,
                        "name": p.name,
                        "size": stat.st_size,
                        "extension": p.suffix.lower(),
                        "modified": stat.st_mtime,
                        "is_text": self._is_text_file(p),
                    })
                except Exception:
                    continue
        return sorted(result, key=lambda x: x["path"])

    def _is_text_file(self, path: Path) -> bool:
        text_exts = {".py", ".js", ".json", ".txt", ".md", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".env", ".html", ".css", ".ts", ".jsx", ".tsx", ".sh", ".bat"}
        if path.suffix.lower() in text_exts:
            return True
        # Try to detect binary
        try:
            with open(path, 'rb') as f:
                chunk = f.read(1024)
                if b'\0' in chunk:
                    return False
            return True
        except Exception:
            return False

    def read_file(self, project_id: int, relative_path: str) -> str:
        path = self._safe_path(project_id, relative_path)
        return path.read_text(errors="replace")

    def write_file(self, project_id: int, relative_path: str, content: str) -> None:
        path = self._safe_path(project_id, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def delete_file(self, project_id: int, relative_path: str) -> bool:
        path = self._safe_path(project_id, relative_path)
        if not path.exists():
            return False
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True

    def rename_file(self, project_id: int, old_path: str, new_path: str) -> bool:
        old = self._safe_path(project_id, old_path)
        new = self._safe_path(project_id, new_path)
        if not old.exists():
            raise FileNotFoundError(f"Source not found: {old_path}")
        if new.exists():
            raise ValueError("Destination already exists")
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        return True

    def get_file_info(self, project_id: int, relative_path: str) -> Dict[str, Any] | None:
        try:
            path = self._safe_path(project_id, relative_path)
            if not path.exists():
                return None
            stat = path.stat()
            return {
                "path": relative_path,
                "name": path.name,
                "size": stat.st_size,
                "extension": path.suffix.lower(),
                "modified": stat.st_mtime,
                "is_dir": path.is_dir(),
            }
        except Exception:
            return None

    def _safe_path(self, project_id: int, relative_path: str) -> Path:
        base = self.project_dir(project_id).resolve()
        # Prevent empty or absolute paths escaping
        if not relative_path or relative_path.startswith("/"):
            # Allow absolute-like but still resolve under base
            relative_path = relative_path.lstrip("/")
        path = (base / relative_path).resolve()
        if not str(path).startswith(str(base)):
            raise ValueError("Path escapes project directory")
        return path

    def ensure_venv(self, project_id: int) -> None:
        venv_dir = self.project_dir(project_id) / ".venv"
        if not venv_dir.exists():
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    def install_requirements(self, project_id: int) -> tuple[bool, str]:
        self.ensure_venv(project_id)
        project_dir = self.project_dir(project_id)
        req = project_dir / "requirements.txt"
        pkg_json = project_dir / "package.json"
        messages: list[str] = []
        ok = True

        if req.exists():
            pip = project_dir / ".venv" / "bin" / "pip"
            result = subprocess.run(
                [str(pip), "install", "-r", str(req)], capture_output=True, text=True, timeout=600
            )
            ok = ok and result.returncode == 0
            messages.append(result.stdout[-1500:] + result.stderr[-1500:])
        else:
            messages.append("No requirements.txt found — skipping Python dependency install.")

        if pkg_json.exists():
            if shutil.which("npm") is None:
                ok = False
                messages.append("package.json found but 'npm' is not installed on this server.")
            else:
                result = subprocess.run(
                    ["npm", "install"], capture_output=True, text=True, cwd=str(project_dir), timeout=600
                )
                ok = ok and result.returncode == 0
                messages.append(result.stdout[-1500:] + result.stderr[-1500:])

        return ok, "\n".join(messages)

    def detect_runtime(self, project_id: int) -> str:
        """Detect runtime based on files present"""
        files = self.list_files(project_id)
        has_py = any(f.endswith(".py") for f in files)
        has_js = any(f.endswith(".js") for f in files)
        has_req = any("requirements.txt" in f for f in files)
        has_pkg = any("package.json" in f for f in files)

        if has_py and has_js:
            return "python+node"
        if has_pkg or (has_js and not has_py):
            return "node"
        if has_py or has_req:
            return "python"
        # Default fallback
        return "python"

    def get_resource_info(self, project_id: int) -> Dict[str, Any]:
        """Get resource usage info if process is running"""
        rt = self._runtime.get(project_id)
        if not rt or not rt.running:
            return {"status": "stopped", "cpu": 0, "memory": 0, "uptime": 0}

        uptime = 0
        if rt.started_at:
            uptime = time.time() - rt.started_at

        # Try to get actual resource usage via ps if available
        mem_mb = 0
        cpu_percent = 0
        try:
            if rt.process and rt.process.pid:
                # Use ps to get rss
                result = subprocess.run(
                    ["ps", "-o", "rss=,pcpu=", "-p", str(rt.process.pid)],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.strip().split()
                    if len(parts) >= 1:
                        mem_kb = int(parts[0])
                        mem_mb = mem_kb / 1024
                    if len(parts) >= 2:
                        cpu_percent = float(parts[1])
        except Exception:
            pass

        return {
            "status": "running",
            "cpu": cpu_percent,
            "memory": mem_mb,
            "memory_limit": self.memory_mb,
            "cpu_limit": self.cpu_seconds,
            "uptime": uptime,
            "pid": rt.process.pid if rt.process else None,
            "restart_count": rt.restart_count,
        }

    async def _autoinstall_for_missing_module(self, project_id: int, stderr_text: str) -> str:
        match = MISSING_MODULE_RE.search(stderr_text)
        if not match:
            return ""
        module = match.group(1).split(".")[0]
        package = MODULE_PACKAGE_MAP.get(module, module)
        pip = self.project_dir(project_id) / ".venv" / "bin" / "pip"
        try:
            proc = await asyncio.create_subprocess_exec(
                str(pip), "install", package,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=120)
        except Exception as exc:
            return f"⚠️ Missing module `{module}` detected but auto-install failed: {exc}"
        if proc.returncode == 0:
            return f"📦 Auto-installed missing package `{package}` (for `{module}`)."
        return f"⚠️ Missing module `{module}` detected but auto-install of `{package}` failed."

    async def start(self, project_id: int, main_file: str) -> tuple[ManagedProject, str]:
        self.ensure_venv(project_id)
        rt = self._runtime.setdefault(project_id, ManagedProject(self.project_dir(project_id)))
        if rt.running:
            return rt, ""

        is_js = main_file.endswith(".js")
        python = self.venv_python(project_id)
        python_bin = str(python) if python.exists() else sys.executable
        interpreter = "node" if is_js else python_bin
        note = ""

        if not is_js:
            # Quick pre-check run to catch an obviously missing import before the long run.
            try:
                pre = await asyncio.create_subprocess_exec(
                    interpreter, main_file,
                    cwd=str(self.project_dir(project_id)),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    _, stderr = await asyncio.wait_for(pre.communicate(), timeout=6)
                    stderr_text = stderr.decode(errors="replace")
                    if pre.returncode not in (0, None) and "ModuleNotFoundError" in stderr_text:
                        note = await self._autoinstall_for_missing_module(project_id, stderr_text)
                except asyncio.TimeoutError:
                    # Didn't exit in 6s — assume it's a genuine long-running bot; kill the probe.
                    pre.kill()
                    await pre.wait()
            except Exception as exc:
                log.warning("Pre-check failed for project %s: %s", project_id, exc)

        rt.process = await asyncio.create_subprocess_exec(
            interpreter,
            main_file,
            cwd=str(self.project_dir(project_id)),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            preexec_fn=_preexec_limits(self.cpu_seconds, self.memory_mb),
        )
        rt.log_lines.clear()
        rt.started_at = time.time()
        rt._reader_task = asyncio.create_task(self._pump_output(rt))
        return rt, note

    async def restart(self, project_id: int, main_file: str) -> tuple[ManagedProject, str]:
        await self.stop(project_id)
        # Small delay
        await asyncio.sleep(0.5)
        rt, note = await self.start(project_id, main_file)
        rt.restart_count += 1
        return rt, note

    async def _pump_output(self, rt: ManagedProject) -> None:
        assert rt.process is not None and rt.process.stdout is not None
        try:
            async for raw_line in rt.process.stdout:
                rt.log_lines.append(raw_line.decode(errors="replace").rstrip("\n"))
        except Exception as exc:  # process pipe closed, etc.
            rt.log_lines.append(f"[log stream ended: {exc}]")

    async def stop(self, project_id: int) -> bool:
        rt = self._runtime.get(project_id)
        if rt is None or not rt.running:
            return False
        assert rt.process is not None
        try:
            pgid = os.getpgid(rt.process.pid)
            os.killpg(pgid, 15)
        except Exception:
            rt.process.terminate()
        try:
            await asyncio.wait_for(rt.process.wait(), timeout=10)
        except asyncio.TimeoutError:
            rt.process.kill()
        rt.started_at = None
        return True

    def status(self, project_id: int) -> str:
        rt = self._runtime.get(project_id)
        return "running" if (rt and rt.running) else "stopped"

    def tail(self, project_id: int, n: int = 200) -> list[str]:
        rt = self._runtime.get(project_id)
        if rt is None:
            return []
        return list(rt.log_lines)[-n:]

    def clear_logs(self, project_id: int) -> bool:
        rt = self._runtime.get(project_id)
        if rt is None:
            return False
        rt.log_lines.clear()
        return True

    def delete(self, project_id: int) -> None:
        shutil.rmtree(self.project_dir(project_id), ignore_errors=True)
        self._runtime.pop(project_id, None)

    def count_all_running(self, owner_id: int | None = None) -> int:
        # If owner_id filtering needed, we need external project list; this counts all runtime
        count = 0
        for rt in self._runtime.values():
            if rt.running:
                count += 1
        return count
