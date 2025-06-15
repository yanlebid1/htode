# services/webapps/Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Install FastAPI and other dependencies
RUN pip install --no-cache-dir fastapi uvicorn jinja2 pydantic redis psycopg2-binary sqlalchemy python-dotenv

# Copy the mini_webapp.py into the container
COPY mini_webapp.py /app/mini_webapp.py

# Expose port 8080 (the FastAPI port)
EXPOSE 8080

ENV PYTHONPATH=/app

# Launch the FastAPI server
CMD ["uvicorn", "mini_webapp:app", "--host", "0.0.0.0", "--port", "8080"]