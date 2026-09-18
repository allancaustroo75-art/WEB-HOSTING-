from __future__ import annotations

import logging

from backend.bot.handlers import BotHostBot
from backend.config import Settings
from backend.database.db import Database
from backend.process.manager import ProcessManager

log = logging.getLogger(__name__)


class BotRunner:
    def __init__(self, db: Database, pm: ProcessManager, settings: Settings) -> None:
        self.settings = settings
        self.bot_host = BotHostBot(db, pm, settings)
        self.application = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.bot_token and (self.settings.admin_user_ids or self.settings.owner_user_id))

    async def start(self) -> None:
        if not self.configured:
            log.warning("BOT_TOKEN or ADMIN_USER_IDS not set; Telegram bot disabled.")
            return
        seed = set(self.settings.admin_user_ids)
        if self.settings.owner_user_id:
            seed.add(self.settings.owner_user_id)
        self.bot_host.db.seed_admins(seed)
        self.application = self.bot_host.build()
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

    async def stop(self) -> None:
        if self.application is None:
            return
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
