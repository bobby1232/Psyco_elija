import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Set

from openai import OpenAI
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
    openai_api_key: str
    openai_model: str
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
    openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        openai_api_key = os.environ.get("CHAT_GPT_TOKEN", "").strip()
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY or CHAT_GPT_TOKEN is required")
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    women_user_ids = parse_user_ids(os.environ.get("WOMEN_USER_IDS", ""))
    min_reply_seconds = int(os.environ.get("MIN_REPLY_SECONDS", "3"))
    return BotConfig(
        token=token,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        women_user_ids=women_user_ids,
        min_reply_seconds=min_reply_seconds,
    )


class EducationBot:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.last_sent: Dict[int, float] = {}
        self.recent_messages: Dict[int, List[str]] = {}
        self.openai_client = OpenAI(api_key=config.openai_api_key)
        self.system_prompt = (
            "Ты опытный психолог-консультант по отношениям и чуткий слушатель. "
            "Отвечай на русском языке, тепло и эмпатично, отражай чувства собеседницы, "
            "задавай один мягкий уточняющий вопрос, если информации мало. "
            "Давай практичные и бережные рекомендации без давления. "
            "Не используй медицинские диагнозы и не заменяй профессиональную помощь."
        )

    def _can_reply(self, user_id: int) -> bool:
        last = self.last_sent.get(user_id)
        if last is None:
            return True
        return (time.time() - last) >= self.config.min_reply_seconds

    def _mark_sent(self, user_id: int) -> None:
        self.last_sent[user_id] = time.time()

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        user = update.effective_user
        if message is None or user is None:
            return
        if self.config.women_user_ids and user.id not in self.config.women_user_ids:
            logging.debug("Skip message from user %s: not in WOMEN_USER_IDS", user.id)
            return
        if message.text:
            history = self.recent_messages.setdefault(user.id, [])
            history.append(message.text)
            if len(history) > 10:
                self.recent_messages[user.id] = history[-10:]
        if not self._can_reply(user.id):
            logging.debug("Skip message from user %s: rate limited", user.id)
            return
        history = self.recent_messages.get(user.id, [])
        if history:
            context = "\n".join(f"{index + 1}. {text}" for index, text in enumerate(history))
            prompt = (
                "Вот последние сообщения участницы (до 10):\n"
                f"{context}\n"
                "Сделай вывод по общей сути и ответь бережно."
            )
        else:
            prompt = "Поддержи участницу, будь чутким слушателем и дай мягкий совет."
        reply = await self._generate_reply(prompt)
        self._mark_sent(user.id)
        await message.reply_text(reply, parse_mode=ParseMode.HTML)

    async def handle_tip(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        await message.reply_text(random.choice(TIPS), parse_mode=ParseMode.HTML)

    async def _generate_reply(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]

        def _request() -> str:
            response = self.openai_client.chat.completions.create(
                model=self.config.openai_model,
                messages=messages,
                max_tokens=180,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()

        try:
            result = await asyncio.to_thread(_request)
            if result:
                return result
        except Exception:
            pass
        return random.choice(TIPS)


def build_application(config: BotConfig) -> Application:
    bot = EducationBot(config)
    application = Application.builder().token(config.token).build()
    application.add_handler(CommandHandler("tip", bot.handle_tip))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    return application


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    config = load_config()
    application = build_application(config)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
