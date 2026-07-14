FROM python:3.11-slim

WORKDIR /app

# Désactiver complètement PIR et optimisations CPU probl\u00e9matiques
ENV FLAGS_enable_pir_api=0
ENV FLAGS_use_mkldnn=0
ENV PADDLE_PDX_INFERENCE_BACKEND=native
ENV PADDLE_USE_TRT=False

# D\u00e9pendances syst\u00e8me
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY parsers.py .

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8100/sante || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8100"]
