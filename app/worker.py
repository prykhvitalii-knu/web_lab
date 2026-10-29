import os
import time
import urllib.request
import urllib.parse
from celery import Celery

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://akatosh_user:akatosh_password@localhost:5672//")

celery_app = Celery(
    "akatosh_tasks",
    broker=RABBITMQ_URL
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

@celery_app.task(name="process_recipe_file")
def process_recipe_file_task(file_path: str, recipe_title: str):
    print(f"[RabbitMQ Worker] Picked up task from queue for file: {file_path}")
    time.sleep(5)
    print(f"[RabbitMQ Worker] Successfully processed file for recipe: {recipe_title}")
    return f"Processed: {recipe_title}"

@celery_app.task(name="send_telegram_notification")
def send_telegram_notification_task(recipe_title: str, style: str, abv: float):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram Task] Token or Chat ID missing, skipping.")
        return "Skipped"

    text = f"🍺 *Новий рецепт пива в Akatosh!*\n\n• *Назва:* {recipe_title}\n• *Стиль:* {style}\n• *ABV:* {abv}%"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req)
        print("[Telegram Task] Notification sent successfully!")
        return "Sent"
    except Exception as e:
        print(f"[Telegram Task] Failed: {e}")
        return f"Failed: {e}"