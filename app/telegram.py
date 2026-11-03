import logging
import os

import httpx


logger = logging.getLogger(__name__)


class TelegramRequestLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "api.telegram.org" not in record.getMessage()


logging.getLogger("httpx").addFilter(TelegramRequestLogFilter())


def send_telegram_notification(recipe_title: str, style: str, abv: float) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        logger.warning("Telegram notification skipped because it is not configured")
        return False

    text = (
        f"New Akatosh beer recipe\n\n"
        f"Name: {recipe_title}\n"
        f"Style: {style}\n"
        f"ABV: {abv}%"
    )
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=5.0,
        )
    except httpx.RequestError:
        logger.warning("Telegram notification request failed")
        return False

    try:
        result = response.json()
    except ValueError:
        logger.warning("Telegram returned an invalid notification response")
        return False

    if not isinstance(result, dict):
        logger.warning("Telegram returned an invalid notification response")
        return False

    if response.is_error or result.get("ok") is not True:
        description = result.get("description")
        if isinstance(description, str):
            description = " ".join(description.split())[:300]
        else:
            description = "No error description provided"
        logger.warning(
            "Telegram rejected notification: code=%s, description=%s",
            result.get("error_code", response.status_code),
            description,
        )
        return False

    return True
