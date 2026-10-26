FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app
ENV HF_HOME=/app/.cache/huggingface
ENV HF_EMBEDDING_MODEL=BAAI/bge-m3

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/agent_service/requirements.txt requirements.txt
# CUDA-enabled torch first so sentence-transformers reuses it (not the CPU
# wheel). cu124 runs on the T4 (CUDA 12.x+). Lets bge-m3 embed queries on GPU
# — query-time embedding was ~seconds on CPU, the dominant per-request cost.
RUN pip install --timeout 600 --retries 10 torch --index-url https://download.pytorch.org/whl/cu124
RUN pip install --timeout 300 --retries 10 -r requirements.txt
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['HF_EMBEDDING_MODEL'])"

COPY shared ./shared
COPY services/__init__.py ./services/__init__.py
COPY services/agent_service ./services/agent_service

EXPOSE 8100
CMD ["uvicorn", "services.agent_service.main:app", "--host", "0.0.0.0", "--port", "8100"]
