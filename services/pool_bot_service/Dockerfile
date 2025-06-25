FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/pool_bot_service/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY services /app/services
COPY common /app/common

# Set Python path
ENV PYTHONPATH=/app

# Default bot name (will be overridden by docker-compose)
ENV BOT_NAME=pool_bot

# Run the pool bot
CMD ["python", "-m", "services.pool_bot_service.app.main"] 