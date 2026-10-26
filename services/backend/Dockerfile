FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

# System deps for asyncpg and bcrypt
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY services/backend/requirements.txt requirements.txt
RUN pip install --timeout 300 --retries 10 -r requirements.txt

# Copy app (build context is the repo root)
COPY shared ./shared
COPY services/__init__.py ./services/__init__.py
COPY services/backend ./services/backend

# Alembic runs from here: `docker compose exec backend alembic upgrade head`
WORKDIR /app/services/backend

# Run
EXPOSE 8000
CMD ["uvicorn", "services.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
