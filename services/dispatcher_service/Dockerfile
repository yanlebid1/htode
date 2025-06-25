FROM python:3.11-slim

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

# Copy the application code
COPY services/dispatcher_service /app/services/dispatcher_service
COPY common /app/common

# Set Python path
ENV PYTHONPATH=/app

# Run the dispatcher bot
CMD ["python", "-m", "services.dispatcher_service.app.main"] 