# services/telegram_service/Dockerfile

FROM python:3.10-slim

# Install system dependencies needed by Camoufox/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgtk-3-0 \
    libasound2 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxext6 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libxshmfence1 \
    libglib2.0-0 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем общие модули
COPY common /app/common

# Копируем код конкретного сервиса
COPY services/telegram_service/app /app/app

# Устанавливаем зависимости
COPY requirements/telegram.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем PYTHONPATH
ENV PYTHONPATH=/app

# Запуск бота
CMD ["python", "-m", "app.main"]
