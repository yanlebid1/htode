# services/notifier_service/Dockerfile

# ARG for Python base image
ARG PYTHON_VERSION=3.11-slim
FROM python:${PYTHON_VERSION}

# 1) Install system dependencies needed by Chromium/Playwright
#    (list may vary depending on your environment):
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
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2) Copy your shared "common" folder (which includes phone_parser, etc.)
COPY common /app/common

# 3) Copy your specific service code
COPY services/notifier_service/app /app/app

# 4) Copy requirements and install
COPY requirements/notifier.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir camoufox[geoip]

# Ensure browserforge headers directory is writable for non-root user
RUN mkdir -p /usr/local/lib/python*/site-packages/browserforge/headers/data \
    && chmod -R a+rwX /usr/local/lib/python*/site-packages/browserforge \
    && chmod -R a+rwX /usr/local/lib/python*/site-packages/camoufox

# 5) Install Playwright + Browsers
#    A) pip install playwright (whatever version you like)
#    B) Then run "playwright install --with-deps chromium"
#RUN pip install --no-cache-dir playwright==1.36.0
#RUN playwright install --with-deps chromium

# Optionally, you can set an environment variable so Playwright knows
#   where to store the browser binaries, or if you want them in the final image
# e.g.: ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 6) Set PYTHONPATH
ENV PYTHONPATH=/app

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /usr/local/lib/python*/site-packages/browserforge /usr/local/lib/python*/site-packages/camoufox

USER appuser

# 7) Final command (Celery worker for the Notifier queue)
CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info", "--queues=notify_queue"]
