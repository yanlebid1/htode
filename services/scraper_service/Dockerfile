# services/scraper_service/Dockerfile

# ARG for Python base image
ARG PYTHON_VERSION=3.11-slim
FROM python:${PYTHON_VERSION}

# Install system dependencies required by Camoufox / headless Firefox and Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libgbm1 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgtk-3-0 libasound2 \
    libx11-6 libx11-xcb1 libxcb1 libxext6 libxrender1 libxtst6 libxi6 libxshmfence1 \
    libglib2.0-0 libpangocairo-1.0-0 libpango-1.0-0 libcairo2 libatspi2.0-0 \
    wget ca-certificates postgresql-client curl unzip && rm -rf /var/lib/apt/lists/*

# Install Chrome (specific version compatible with AdsPower)
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver version 134 (compatible with AdsPower Chrome 134)
RUN mkdir -p /tmp/chromedriver-linux64 \
    && wget -O /tmp/chromedriver-linux64.zip "https://storage.googleapis.com/chrome-for-testing-public/134.0.6998.36/linux64/chromedriver-linux64.zip" \
    && unzip /tmp/chromedriver-linux64.zip -d /tmp/ \
    && chmod +x /tmp/chromedriver-linux64/chromedriver \
    && rm /tmp/chromedriver-linux64.zip

WORKDIR /app

# Copy shared and service code
COPY common /app/common
COPY services/scraper_service /app/scraper_service
# Include maintenance tasks and other shared utilities
COPY system /app/system

# Copy requirements first for better caching
COPY services/scraper_service/requirements.txt /app/requirements.txt
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
