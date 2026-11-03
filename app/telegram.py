import logging
import os

import httpx


logger = logging.getLogger(__name__)


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

    if response.is_error:
        logger.warning(
            "Telegram notification failed with HTTP status %s",
            response.status_code,
        )
        return False

    try:
        result = response.json()
    except ValueError:
        logger.warning("Telegram returned an invalid notification response")
        return False

    if result.get("ok") is not True:
        logger.warning(
            "Telegram rejected notification: code=%s, description=%s",
            result.get("error_code"),
            result.get("description"),
        )
        return False

    return True
