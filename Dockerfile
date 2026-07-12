FROM python:3.11-slim

WORKDIR /app

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Installer setuptools et wheel
RUN pip install setuptools wheel

# Copier requirements.txt
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY server.py .
COPY parsers.py .

# Pré-télécharger le modèle SERVER au build (plus précis que medium, pas de bug strides)
RUN python -c "from paddleocr import PaddleOCR; ocr = PaddleOCR(lang='fr', use_textline_orientation=True, det_model='PP-OCRv6_server_det', rec_model='PP-OCRv6_server_rec'); print('Modele PP-OCRv6 Server telecharge')"

# Exposer le port
EXPOSE 8100

# Healthcheck pour Coolify
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8100/sante || exit 1

# Lancer le serveur
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8100"]
