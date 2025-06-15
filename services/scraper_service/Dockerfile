# services/scraper_service/Dockerfile

# ARG for Python base image
ARG PYTHON_VERSION=3.11-slim
FROM python:${PYTHON_VERSION}

# Install system dependencies required by Camoufox / headless Firefox
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libgbm1 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgtk-3-0 libasound2 \
    libx11-6 libx11-xcb1 libxcb1 libxext6 libxrender1 libxtst6 libxi6 libxshmfence1 \
    libglib2.0-0 libpangocairo-1.0-0 libpango-1.0-0 libcairo2 libatspi2.0-0 \
    wget ca-certificates postgresql-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy shared and service code
COPY common /app/common
COPY services/scraper_service /app/scraper_service
# Include maintenance tasks and other shared utilities
COPY system /app/system

# Python deps
COPY requirements/scraper.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir camoufox[geoip]

# Make BrowserForge/Camoufox dirs writable for non-root user (GeoIP + headers caches)
RUN mkdir -p /usr/local/lib/python*/site-packages/browserforge/headers/data \
    && chmod -R a+rwX /usr/local/lib/python*/site-packages/browserforge \
    && chmod -R a+rwX /usr/local/lib/python*/site-packages/camoufox

ENV PYTHONPATH=/app

# Create unprivileged user and switch
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /usr/local/lib/python*/site-packages/browserforge /usr/local/lib/python*/site-packages/camoufox

USER appuser

CMD ["celery", "-A", "app.celery_app.celery_app", "worker", "--loglevel=info", "-Q", "scrape_queue"]
