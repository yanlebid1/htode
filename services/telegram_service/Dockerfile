# services/telegram_service/Dockerfile

# ARG for Python base image
ARG PYTHON_VERSION=3.11-slim
FROM python:${PYTHON_VERSION}

# Install system dependencies required by Camoufox / headless Firefox
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libgbm1 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgtk-3-0 libasound2 \
    libx11-6 libx11-xcb1 libxcb1 libxext6 libxrender1 libxtst6 libxi6 libxshmfence1 \
    libglib2.0-0 libpangocairo-1.0-0 libpango-1.0-0 libcairo2 libatspi2.0-0 \
    wget ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем общие модули
COPY common /app/common

# Include maintenance package
COPY system /app/system

# Копируем код конкретного сервиса
COPY services/telegram_service/app /app/app

# Устанавливаем зависимости
COPY requirements/telegram.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir camoufox[geoip]

# Make BrowserForge/Camoufox dirs writable
RUN mkdir -p /usr/local/lib/python*/site-packages/browserforge/headers/data \
    && chmod -R a+rwX /usr/local/lib/python*/site-packages/browserforge \
    && chmod -R a+rwX /usr/local/lib/python*/site-packages/camoufox

# Устанавливаем PYTHONPATH
ENV PYTHONPATH=/app

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /usr/local/lib/python*/site-packages/browserforge /usr/local/lib/python*/site-packages/camoufox

USER appuser

# Запуск бота
CMD ["python", "-m", "app.main"]
