from __future__ import annotations

import logging
import time

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from backend.config import Settings
from backend.database.db import Database
from backend.process.manager import ProcessManager
from backend.services.naming import is_allowed_upload, sanitize_filename, sanitize_slug

log = logging.getLogger(__name__)

# Persistent reply-keyboard button labels
BTN_MY_FILES = "📁 My Files"
BTN_UPLOAD_FILE = "📤 Upload File"
BTN_EDIT_FILES = "✏️ Edit Files"
BTN_DELETE_FOLDER = "🗑️ Delete Folder"
BTN_RUN_MODULE = "▶️ Run Module"
BTN_STATUS = "📊 Status"
BTN_MY_LOGS = "📋 My Logs"
BTN_REVOKE_TOKEN = "🔄 Revoke Token"
BTN_WEB_DASHBOARD = "🌐 Web Dashboard"
BTN_OPEN_PANEL = "🚀 Open Hosting Panel"

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [BTN_OPEN_PANEL],
        [BTN_MY_FILES, BTN_UPLOAD_FILE],
        [BTN_EDIT_FILES, BTN_DELETE_FOLDER],
        [BTN_RUN_MODULE, BTN_STATUS],
        [BTN_MY_LOGS, BTN_REVOKE_TOKEN],
        [BTN_WEB_DASHBOARD],
    ],
    resize_keyboard=True,
)


def _is_owner(settings: Settings, user_id: int) -> bool:
    return settings.owner_user_id != 0 and user_id == settings.owner_user_id


class BotHostBot:
    def __init__(self, db: Database, pm: ProcessManager, settings: Settings) -> None:
        self.db = db
        self.pm = pm
        self.settings = settings
        self.application: Application | None = None
        self._pending_uploads: dict[int, dict] = {}  # user_id -> {filename, content}
        self._pending_edits: dict[int, dict] = {}  # user_id -> {project_id, path}

    def build(self) -> Application:
        app = Application.builder().token(self.settings.bot_token).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("panel", self.cmd_panel))
        app.add_handler(CommandHandler("hosting", self.cmd_panel))
        app.add_handler(CommandHandler("myfiles", self.cmd_myfiles))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("dashboard", self.cmd_dashboard))
        app.add_handler(CommandHandler("addadmin", self.cmd_add_admin))
        app.add_handler(CommandHandler("removeadmin", self.cmd_remove_admin))
        app.add_handler(CommandHandler("listadmins", self.cmd_list_admins))
        app.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        app.add_handler(MessageHandler(filters.Document.ALL, self.on_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        app.add_handler(CallbackQueryHandler(self.on_callback))
        self.application = app
        return app

    def _guard(self, update: Update) -> bool:
        user = update.effective_user
        if not user:
            return False
        # If ADMIN_USER_IDS is empty, allow all? For Mini App we want to allow all users
        # But for legacy bot commands, we preserve admin check if list is non-empty
        # If no admin list configured, allow everyone (open hosting)
        if not self.settings.admin_user_ids and self.settings.owner_user_id == 0:
            return True
        return self.db.is_admin(user.id) or user.id == self.settings.owner_user_id or user.id in self.settings.admin_user_ids

    def _guard_miniapp(self, user_id: int) -> bool:
        # Mini App is open to all authenticated Telegram users
        # If you want admin-only, enforce here
        return True

    def _get_mini_app_keyboard(self) -> InlineKeyboardMarkup:
        mini_app_url = self.settings.mini_app_url or self.settings.dashboard_base_url
        # Ensure URL is HTTPS for Telegram WebApp (required in production, but localhost allowed for dev)
        buttons = []
        if mini_app_url:
            try:
                # Telegram requires https for WebApp, but we still create button
                buttons.append([InlineKeyboardButton("🚀 Open Hosting Panel", web_app=WebAppInfo(url=mini_app_url))])
            except Exception:
                # Fallback to regular URL button if web_app fails
                buttons.append([InlineKeyboardButton("🚀 Open Hosting Panel", url=mini_app_url)])
        # Add fallback dashboard link
        buttons.append([InlineKeyboardButton("📊 My Projects", callback_data="myfiles:0")])
        buttons.append([InlineKeyboardButton("🌐 Legacy Dashboard", callback_data="dashboard")])
        return InlineKeyboardMarkup(buttons)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._guard(update):
            await update.message.reply_text("This bot is private. Contact owner for access.")
            return
        user = update.effective_user
        self.db.record_active_user(user.id)
        # Upsert telegram user profile
        try:
            self.db.upsert_telegram_user(
                user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
            )
        except Exception:
            pass

        mini_app_url = self.settings.mini_app_url or self.settings.dashboard_base_url

        welcome_text = (
            "🚀 *Welcome to SNUKED HOSTER — Premium Bot Hosting*\\n\\n"
            "Host your Python & Node.js bots directly from Telegram\\!\\n\\n"
            "✨ *What you can do:*\\n"
            "• 📤 Upload \\.py, \\.js, or \\.zip files\\n"
            "• ▶️ Start / Stop / Restart with one tap\\n"
            "• 📁 File manager & code editor\\n"
            "• 📋 Live logs & monitoring\\n"
            "• 🌐 Premium dashboard inside Telegram\\n\\n"
            "👇 *Tap below to open your hosting panel*\\n\\n"
            "Or send me a file to create a project instantly\\."
        )

        # Send with Mini App button
        keyboard = self._get_mini_app_keyboard()

        await update.message.reply_text(
            welcome_text,
            parse_mode="MarkdownV2",
            reply_markup=keyboard,
        )

        # Also send the persistent menu
        await update.message.reply_text(
            "Use the menu below anytime or type /panel to open hosting panel:",
            reply_markup=MAIN_MENU,
        )

    async def cmd_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._guard(update):
            await update.message.reply_text("This bot is private.")
            return
        self.db.record_active_user(update.effective_user.id)
        mini_app_url = self.settings.mini_app_url or self.settings.dashboard_base_url

        if not mini_app_url:
            await update.message.reply_text("⚠️ Mini App URL not configured. Set MINI_APP_URL in environment.")
            return

        keyboard = self._get_mini_app_keyboard()
        await update.message.reply_text(
            "🚀 *SNUKED HOSTER Hosting Panel*\\n\\n"
            "Tap the button below to open your premium hosting dashboard inside Telegram\\!\\n\\n"
            "• Manage projects\\n"
            "• Edit files\\n"
            "• View live logs\\n"
            "• Start/Stop bots\\n\\n"
            f"URL: {mini_app_url}",
            parse_mode="MarkdownV2",
            reply_markup=keyboard,
        )

    async def cmd_add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_owner(self.settings, update.effective_user.id):
            await update.message.reply_text("Owner only.")
            return
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("Usage: /addadmin <telegram_user_id>")
            return
        new_admin_id = int(context.args[0])
        self.db.add_admin(new_admin_id)
        await update.message.reply_text(f"✅ Added admin: {new_admin_id}")

    async def cmd_remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_owner(self.settings, update.effective_user.id):
            await update.message.reply_text("Owner only.")
            return
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("Usage: /removeadmin <telegram_user_id>")
            return
        target_id = int(context.args[0])
        if target_id == self.settings.owner_user_id:
            await update.message.reply_text("❌ Can't remove the owner.")
            return
        removed = self.db.remove_admin(target_id)
        await update.message.reply_text("✅ Removed." if removed else "That ID wasn't an admin.")

    async def cmd_list_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._guard(update):
            return
        admins = sorted(self.db.list_admins())
        lines = [f"• `{a}`" + (" (owner)" if a == self.settings.owner_user_id else "") for a in admins]
        await update.message.reply_text("*Admins:*\\n" + "\\n".join(lines), parse_mode="Markdown")

    async def cmd_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_owner(self.settings, update.effective_user.id):
            await update.message.reply_text("Owner only.")
            return
        text = " ".join(context.args) if context.args else ""
        if not text:
            await update.message.reply_text("Usage: /broadcast <message>")
            return
        recipients = self.db.list_active_users()
        sent, failed = 0, 0
        for uid in recipients:
            try:
                await context.bot.send_message(uid, f"📢 {text}")
                sent += 1
            except Exception:
                failed += 1
        await update.message.reply_text(f"Broadcast sent: {sent} ok, {failed} failed.")

    async def on_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._guard(update):
            return
        doc = update.message.document
        filename = sanitize_filename(doc.file_name or "file")
        if not is_allowed_upload(filename):
            await update.message.reply_text(
                "❌ Unsupported file type. Send a .py, .js, .txt, .json or .zip file."
            )
            return
        if doc.file_size and doc.file_size > self.settings.max_upload_bytes:
            await update.message.reply_text("❌ File too large.")
            return

        tg_file = await doc.get_file()
        content = bytes(await tg_file.download_as_bytearray())
        user_id = update.effective_user.id
        self._pending_uploads[user_id] = {"filename": filename, "content": content}
        await update.message.reply_text("📝 Enter a project name (or tap 🚀 Open Hosting Panel to manage in Mini App):")

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._guard(update):
            return
        user_id = update.effective_user.id
        text = update.message.text.strip()

        # 1) Finishing a file-content edit (Edit Files flow)?
        pending_edit = self._pending_edits.get(user_id)
        if pending_edit is not None:
            del self._pending_edits[user_id]
            try:
                self.pm.write_file(pending_edit["project_id"], pending_edit["path"], update.message.text)
                self.db.add_activity("edit_file", str(user_id), pending_edit["project_id"], pending_edit["path"])
                await update.message.reply_text(f"✅ Saved `{pending_edit['path']}`.", parse_mode="Markdown")
            except ValueError:
                await update.message.reply_text("❌ Invalid file path.")
            return

        # 2) Main menu button taps.
        if text == BTN_OPEN_PANEL:
            await self.cmd_panel(update, context)
            return
        if text == BTN_MY_FILES:
            await self._send_project_list(update.effective_chat.id, user_id, context)
            return
        if text == BTN_UPLOAD_FILE:
            await update.message.reply_text("📤 Send me a .py, .txt, .json or .zip file to get started. Or use 🚀 Open Hosting Panel for advanced upload.")
            return
        if text == BTN_EDIT_FILES:
            await self._send_project_picker(update.effective_chat.id, user_id, context, "editfiles", "Pick a project to edit:")
            return
        if text == BTN_DELETE_FOLDER:
            await self._send_project_picker(update.effective_chat.id, user_id, context, "delete", "Pick a project to delete:")
            return
        if text == BTN_RUN_MODULE:
            await self._send_project_picker(update.effective_chat.id, user_id, context, "start", "Pick a project to run:")
            return
        if text == BTN_STATUS:
            await self._reply_status(update.effective_chat.id, user_id, context)
            return
        if text == BTN_MY_LOGS:
            await self._send_project_picker(update.effective_chat.id, user_id, context, "logs", "Pick a project for logs:")
            return
        if text == BTN_REVOKE_TOKEN:
            count = self.db.revoke_all_tokens(user_id)
            await update.message.reply_text(
                f"🔄 Revoked {count} outstanding dashboard link(s). Use /dashboard for a fresh one."
            )
            return
        if text == BTN_WEB_DASHBOARD:
            await self._send_dashboard_link(update.effective_chat.id, user_id, context)
            return

        # 3) Otherwise, treat as the project name after a file upload.
        pending = self._pending_uploads.pop(user_id, None)
        if pending is None:
            return  # not in the middle of an upload flow; ignore stray text

        if self.db.count_projects(user_id) >= self.settings.max_projects_per_user:
            await update.message.reply_text(
                f"❌ Project limit reached ({self.settings.max_projects_per_user}). "
                "Delete a project first with My Files or in the Mini App."
            )
            return

        name = update.message.text.strip()[:64]
        slug = sanitize_slug(f"{user_id}-{name}-{int(time.time())}")
        project = self.db.create_project(user_id, name, slug)
        project_id = project["id"]

        try:
            self.pm.save_upload(project_id, pending["filename"], pending["content"])
        except ValueError as exc:
            self.pm.delete(project_id)
            self.db.delete_project(project_id)
            await update.message.reply_text(f"❌ Rejected: {exc}")
            return
        main_file = pending["filename"] if pending["filename"].endswith((".py", ".js")) else None
        if main_file is None:
            # Zip upload: guess an entrypoint if one is obviously present.
            candidates = [
                f for f in self.pm.list_files(project_id)
                if f.endswith(("main.py", "bot.py", "app.py", "index.js", "main.js", "bot.js"))
            ]
            main_file = candidates[0] if candidates else None
        self.db.update_project(project_id, main_file=main_file)
        self.db.add_file(project_id, pending["filename"], len(pending["content"]))

        await update.message.reply_text("📦 Installing dependencies…")
        ok, log_tail = self.pm.install_requirements(project_id)
        status_line = "✅ All dependencies OK" if ok else f"⚠️ Dependency install had issues:\\n{log_tail[-500:]}"

        self.db.add_activity("upload", str(user_id), project_id, pending["filename"])

        keyboard = self._get_mini_app_keyboard()
        await update.message.reply_text(
            f"✅ *File Uploaded!*\\n\\n"
            f"Project: *{name}*\\n"
            f"File: `{pending['filename']}`\\n"
            f"Size: {len(pending['content']) / 1024:.1f} KB\\n"
            f"{status_line}\\n\\n"
            "Use 📂 My Files or 🚀 Open Hosting Panel to manage it.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    async def cmd_myfiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._guard(update):
            return
        await self._send_project_list(update.effective_chat.id, update.effective_user.id, context)

    async def _send_project_list(self, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        projects = self.db.list_projects(user_id)
        if not projects:
            keyboard = self._get_mini_app_keyboard()
            await context.bot.send_message(chat_id, "You have no projects yet. Send me a file or open the Hosting Panel!", reply_markup=keyboard)
            return
        running = sum(1 for p in projects if self.pm.status(p["id"]) == "running")
        lines = [f"*Your Projects* ({len(projects)} total)", ""]
        buttons = []
        for p in projects:
            status = self.pm.status(p["id"])
            dot = "🟢" if status == "running" else "⚪"
            buttons.append([InlineKeyboardButton(f"{dot} {p['name']}", callback_data=f"project:{p['id']}")])
        lines.append(f"Running: {running} / {len(projects)}")
        # Add Mini App button
        mini_app_url = self.settings.mini_app_url or self.settings.dashboard_base_url
        if mini_app_url:
            try:
                buttons.append([InlineKeyboardButton("🚀 Open Hosting Panel", web_app=WebAppInfo(url=mini_app_url))])
            except Exception:
                buttons.append([InlineKeyboardButton("🚀 Open Hosting Panel", url=mini_app_url)])
        await context.bot.send_message(
            chat_id, "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._guard(update):
            return
        await self._reply_status(update.effective_chat.id, update.effective_user.id, context)

    async def _reply_status(self, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        projects = self.db.list_projects(user_id)
        running = sum(1 for p in projects if self.pm.status(p["id"]) == "running")
        await context.bot.send_message(
            chat_id,
            "*Your Status*\\n\\n"
            f"Projects: {len(projects)}\\n"
            f"Running: {running}\\n"
            f"Limit: {len(projects)}/{self.settings.max_projects_per_user}",
            parse_mode="Markdown",
        )

    async def _send_project_picker(
        self, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE, action_prefix: str, title: str
    ) -> None:
        projects = self.db.list_projects(user_id)
        if not projects:
            await context.bot.send_message(chat_id, "You have no projects yet.")
            return
        buttons = [
            [InlineKeyboardButton(p["name"], callback_data=f"{action_prefix}:{p['id']}")] for p in projects
        ]
        await context.bot.send_message(chat_id, title, reply_markup=InlineKeyboardMarkup(buttons))

    async def cmd_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._guard(update):
            return
        await self._send_dashboard_link(update.effective_chat.id, update.effective_user.id, context)

    async def _send_dashboard_link(self, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Legacy dashboard link
        token = self.db.create_login_token(user_id, self.settings.login_token_ttl_seconds)
        legacy_url = f"{self.settings.dashboard_base_url}/login.html?token={token}"
        mini_app_url = self.settings.mini_app_url or self.settings.dashboard_base_url
        minutes = self.settings.login_token_ttl_seconds // 60

        keyboard = self._get_mini_app_keyboard()

        await context.bot.send_message(
            chat_id,
            "🌐 *Hosting Dashboard Access*\\n\\n"
            f"🚀 *Mini App (Recommended):*\\n{mini_app_url}\\n\\n"
            f"🔗 *Legacy Web Dashboard:*\\n{legacy_url}\\n\\n"
            f"Legacy link expires in {minutes} minutes.\\n"
            "Mini App uses secure Telegram authentication automatically.",
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        user = update.effective_user
        if not user or not self._guard(update):
            await query.answer("Not authorized.", show_alert=True)
            return
        await query.answer()
        data = query.data or ""

        if data == "dashboard":
            await self._send_dashboard_link(query.message.chat_id, user.id, context)
            return
        if data.startswith("myfiles"):
            await self._send_project_list(query.message.chat_id, user.id, context)
            return
        if data.startswith("noop"):
            return

        if data.startswith("project:"):
            project_id = int(data.split(":", 1)[1])
            await self._send_project_detail(query.message.chat_id, project_id, context)
            return

        if data.startswith("logs:"):
            project_id = int(data.split(":", 1)[1])
            project = self.db.get_project(project_id)
            if not project or project["owner_id"] != user.id:
                await context.bot.send_message(query.message.chat_id, "Project not found.")
                return
            lines = self.pm.tail(project_id, 60)
            body = "\n".join(lines) if lines else "(no output yet — start the project first)"
            await context.bot.send_message(
                query.message.chat_id, f"📋 *Logs — {project['name']}*\\n```\\n{body[-3500:]}\\n```", parse_mode="Markdown"
            )
            return

        if data.startswith("editfiles:"):
            project_id = int(data.split(":", 1)[1])
            project = self.db.get_project(project_id)
            if not project or project["owner_id"] != user.id:
                await context.bot.send_message(query.message.chat_id, "Project not found.")
                return
            files = self.pm.list_files(project_id)
            if not files:
                await context.bot.send_message(query.message.chat_id, "No files in this project.")
                return
            buttons = [
                [InlineKeyboardButton(f, callback_data=f"editfile:{project_id}:{i}")]
                for i, f in enumerate(files)
            ]
            context.chat_data[f"files:{project_id}"] = files
            await context.bot.send_message(query.message.chat_id, "Pick a file to edit:", reply_markup=InlineKeyboardMarkup(buttons))
            return

        if data.startswith("editfile:"):
            _, project_id_raw, index_raw = data.split(":", 2)
            project_id = int(project_id_raw)
            files = context.chat_data.get(f"files:{project_id}") or self.pm.list_files(project_id)
            index = int(index_raw)
            if index >= len(files):
                await context.bot.send_message(query.message.chat_id, "File list expired, tap ✏️ Edit Files again.")
                return
            path = files[index]
            try:
                content = self.pm.read_file(project_id, path)
            except Exception:
                await context.bot.send_message(query.message.chat_id, "Could not read that file.")
                return
            self._pending_edits[user.id] = {"project_id": project_id, "path": path}
            preview = content if len(content) <= 3500 else content[:3500] + "\n…(truncated)"
            await context.bot.send_message(
                query.message.chat_id,
                f"✏️ *{path}* — current content:\\n```\\n{preview}\\n```\\n\\nReply with the new full content to save it.",
                parse_mode="Markdown",
            )
            return

        if data.startswith("start:") or data.startswith("stop:") or data.startswith("delete:"):
            action, raw_id = data.split(":", 1)
            project_id = int(raw_id)
            project = self.db.get_project(project_id)
            if not project or project["owner_id"] != user.id:
                await context.bot.send_message(query.message.chat_id, "Project not found.")
                return
            if action == "start":
                if not project["main_file"]:
                    await context.bot.send_message(query.message.chat_id, "❌ No entrypoint (.py) found for this project.")
                    return
                _, note = await self.pm.start(project_id, project["main_file"])
                self.db.update_project(project_id, status="running")
                self.db.add_activity("start", str(user.id), project_id)
                msg = f"▶️ Started *{project['name']}*"
                if note:
                    msg += f"\n{note}"
                await context.bot.send_message(query.message.chat_id, msg, parse_mode="Markdown")
            elif action == "stop":
                await self.pm.stop(project_id)
                self.db.update_project(project_id, status="stopped")
                self.db.add_activity("stop", str(user.id), project_id)
                await context.bot.send_message(query.message.chat_id, f"⏹ Stopped *{project['name']}*", parse_mode="Markdown")
            elif action == "delete":
                await self.pm.stop(project_id)
                self.db.add_activity("delete", str(user.id), project_id, project['name'])
                self.pm.delete(project_id)
                self.db.delete_project(project_id)
                await context.bot.send_message(query.message.chat_id, f"🗑 Deleted *{project['name']}*", parse_mode="Markdown")
            return

    async def _send_project_detail(self, chat_id: int, project_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        project = self.db.get_project(project_id)
        if not project:
            await context.bot.send_message(chat_id, "Project not found.")
            return
        status = self.pm.status(project_id)
        files = self.db.list_files(project_id)
        buttons = [
            [
                InlineKeyboardButton("▶️ Start", callback_data=f"start:{project_id}"),
                InlineKeyboardButton("⏹ Stop", callback_data=f"stop:{project_id}"),
            ],
            [InlineKeyboardButton("🗑 Delete Project", callback_data=f"delete:{project_id}")],
            [InlineKeyboardButton("« Back", callback_data="myfiles:0")],
        ]
        mini_app_url = self.settings.mini_app_url or self.settings.dashboard_base_url
        if mini_app_url:
            try:
                buttons.insert(0, [InlineKeyboardButton("🚀 Open in Hosting Panel", web_app=WebAppInfo(url=mini_app_url))])
            except Exception:
                pass
        await context.bot.send_message(
            chat_id,
            f"*{project['name']}*\\n\\n"
            f"Status: {'🟢 running' if status == 'running' else '⚪ stopped'}\\n"
            f"Entrypoint: `{project['main_file'] or 'not set'}`\\n"
            f"Files: {len(files)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
