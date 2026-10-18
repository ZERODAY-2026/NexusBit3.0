# LexLocal + Ollama in one image, for the --network none offline demo (see docs/DOCKER.md).
# Build (online, once):   docker build -t lexlocal .
# Gemma weights are NOT baked in: mount your host's Ollama model store read-only at run time.
ARG OLLAMA_VERSION=0.40.6
FROM ollama/ollama:${OLLAMA_VERSION}

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    LEXLOCAL_NETGUARD=strict HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
    OLLAMA_HOST=127.0.0.1:11434

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /venv \
    && /venv/bin/pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
    && /venv/bin/pip install -r requirements.txt
ENV PATH=/venv/bin:$PATH

COPY . .
# Setup-time downloads (embedding model). After this the image needs no network.
RUN python scripts/download_models.py && python scripts/make_samples.py

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8501
ENTRYPOINT ["/entrypoint.sh"]
CMD ["app"]
