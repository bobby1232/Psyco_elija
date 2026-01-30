import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Set

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


TIPS: List[str] = [
    "Замечайте свои эмоции: назовите чувство вслух — это снижает его интенсивность.",
    "Говорите через 'я-сообщения': 'я чувствую…' вместо 'ты всегда…'.",
    "Сохраняйте паузу перед ответом — 3 глубоких вдоха помогают вернуть ясность.",
    "Формулируйте просьбы конкретно: что, когда и как было бы полезно.",
    "Практикуйте благодарность: ежедневно фиксируйте 3 вещи, за которые благодарны.",
    "Отделяйте факт от интерпретации: 'Он не ответил 2 часа' ≠ 'Ему всё равно'.",
    "Дайте себе право на отдых без чувства вины — это ресурс для семьи.",
    "Ставьте границы мягко: 'Мне важно… поэтому я…'.",
]


@dataclass
class BotConfig:
    token: str
    women_user_ids: Set[int]
    min_reply_seconds: int


def parse_user_ids(raw: str) -> Set[int]:
    if not raw:
        return set()
    return {int(value.strip()) for value in raw.split(",") if value.strip().isdigit()}


def load_config() -> BotConfig:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")
    women_user_ids = parse_user_ids(os.environ.get("WOMEN_USER_IDS", ""))
    min_reply_seconds = int(os.environ.get("MIN_REPLY_SECONDS", "3600"))
    return BotConfig(
        token=token,
        women_user_ids=women_user_ids,
        min_reply_seconds=min_reply_seconds,
    )


class EducationBot:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.last_sent: Dict[int, float] = {}

    def _can_reply(self, user_id: int) -> bool:
        last = self.last_sent.get(user_id)
        if last is None:
            return True
        return (time.time() - last) >= self.config.min_reply_seconds

    def _mark_sent(self, user_id: int) -> None:
        self.last_sent[user_id] = time.time()

    async def send_tip(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            return
        if user.id not in self.config.women_user_ids:
            await update.effective_message.reply_text(
                "Эта команда предназначена для участниц группы.",
            )
            return
        tip = random.choice(TIPS)
        self._mark_sent(user.id)
        await update.effective_message.reply_text(tip, parse_mode=ParseMode.HTML)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        user = update.effective_user
        if message is None or user is None:
            return
        if user.id not in self.config.women_user_ids:
            return
        if not self._can_reply(user.id):
            return
        tip = random.choice(TIPS)
        self._mark_sent(user.id)
        await message.reply_text(tip, parse_mode=ParseMode.HTML)


def build_application(config: BotConfig) -> Application:
    bot = EducationBot(config)
    application = Application.builder().token(config.token).build()
    application.add_handler(CommandHandler("tip", bot.send_tip))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    return application


def main() -> None:
    config = load_config()
    application = build_application(config)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
