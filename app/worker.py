import os
import time
from celery import Celery

from .telegram import send_telegram_notification

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://akatosh_user:akatosh_password@localhost:5672//")

celery_app = Celery(
    "akatosh_tasks",
    broker=RABBITMQ_URL
)

@celery_app.task(name="process_recipe_file")
def process_recipe_file_task(file_path: str, recipe_title: str):
    print(f"[RabbitMQ Worker] Picked up task from queue for file: {file_path}")
    time.sleep(5)
    print(f"[RabbitMQ Worker] Successfully processed file for recipe: {recipe_title}")
    return f"Processed: {recipe_title}"

@celery_app.task(name="send_telegram_notification")
def send_telegram_notification_task(recipe_title: str, style: str, abv: float):
    sent = send_telegram_notification(recipe_title, style, abv)
    return "Sent" if sent else "Failed"