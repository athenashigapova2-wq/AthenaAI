FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/athena/.cache/huggingface

WORKDIR /app

# libgomp is required by the local sentence-transformers/scikit-learn stack.
# Tesseract is the local OCR adapter; application code still depends on an
# interface, so a managed OCR provider can replace it without changing policy.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libgomp1 \
        fonts-dejavu-core \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

RUN useradd --create-home --uid 10001 athena \
    && mkdir -p /home/athena/.cache/huggingface \
    && chown -R athena:athena /home/athena
COPY --chown=athena:athena app ./app
COPY --chown=athena:athena evaluation/document_ocr ./evaluation/document_ocr
COPY --chown=athena:athena scripts/run_ocr_backend_benchmark.py ./scripts/run_ocr_backend_benchmark.py
COPY --chown=athena:athena scripts/evaluate_document_ocr.py ./scripts/evaluate_document_ocr.py

USER athena

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
