FROM python:3.11-slim

WORKDIR /app

# Dépendances système nécessaires
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1-mesa-glx \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Installer setuptools d'abord (évite erreurs Python 3.12)
RUN pip install setuptools wheel

# Installer PaddlePaddle CPU
RUN pip install paddlepaddle==3.0.0 \
    -i https://www.paddlepaddle.org.cn/packages/stable/cpu/

# Installer PaddleOCR 3.7
RUN pip install paddleocr==3.7.0

# Installer FastAPI et dépendances
RUN pip install \
    fastapi==0.115.0 \
    uvicorn==0.30.0 \
    pillow==10.4.0 \
    python-multipart==0.0.9

# Copier les fichiers
COPY server.py .
COPY parsers.py .

# Pré-télécharger le modèle Medium au build
# (évite le délai au premier appel)
RUN python -c "
from paddleocr import PaddleOCR
ocr = PaddleOCR(
    use_angle_cls=True,
    lang='fr',
    use_gpu=False,
    show_log=False,
    ocr_version='PP-OCRv4'
)
print('Modèle PP-OCRv6 Medium téléchargé')
"

EXPOSE 8100

# Healthcheck
HEALTHCHECK --interval=30s \
            --timeout=10s \
            --start-period=60s \
            --retries=3 \
  CMD wget -qO- http://localhost:8100/sante || exit 1

CMD ["uvicorn", "server:app", \
     "--host", "0.0.0.0", \
     "--port", "8100", \
     "--workers", "1"]