FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app
ENV HF_HOME=/app/.cache/huggingface
ENV HF_EMBEDDING_MODEL=BAAI/bge-m3

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/pipeline_worker/requirements.txt requirements.txt
# Install CUDA-enabled torch first so sentence-transformers reuses it instead of
# pulling the CPU-only wheel. cu124 matches the L4 driver (CUDA 12.x+).
RUN pip install --timeout 600 --retries 10 torch --index-url https://download.pytorch.org/whl/cu124
RUN pip install --timeout 300 --retries 10 -r requirements.txt
RUN python -m playwright install --with-deps chromium
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['HF_EMBEDDING_MODEL'])"

COPY shared ./shared
COPY services/__init__.py ./services/__init__.py
COPY services/pipeline_worker ./services/pipeline_worker
COPY etl/__init__.py ./etl/__init__.py
COPY etl/crawler ./etl/crawler
COPY etl/data_pipeline ./etl/data_pipeline

EXPOSE 8200
CMD ["uvicorn", "services.pipeline_worker.main:app", "--host", "0.0.0.0", "--port", "8200"]
