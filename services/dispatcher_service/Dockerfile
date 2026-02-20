FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/dispatcher_service/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd -m -u 1000 appuser

# Copy the application code
COPY --chown=appuser:appuser services/dispatcher_service /app/services/dispatcher_service
COPY --chown=appuser:appuser common /app/common

# Set Python path
ENV PYTHONPATH=/app

USER appuser

# Run the dispatcher bot
CMD ["python", "-m", "services.dispatcher_service.app.main"]
