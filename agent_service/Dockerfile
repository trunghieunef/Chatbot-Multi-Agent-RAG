FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app:/app/backend
ENV HF_HOME=/app/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY agent_service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_service ./agent_service
COPY backend ./backend

EXPOSE 8100
CMD ["uvicorn", "agent_service.main:app", "--host", "0.0.0.0", "--port", "8100"]
