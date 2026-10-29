FROM python:3.11-slim

# 1. Оптимізація роботи Python в контейнері
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 1001 akatosh && \
    adduser --system --uid 1001 --gid 1001 --no-create-home akatosh && \
    mkdir -p /app/uploads && \
    chown -R akatosh:akatosh /app

COPY --chown=akatosh:akatosh requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY --chown=akatosh:akatosh . .

USER akatosh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]