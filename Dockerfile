FROM python:3.11-slim

WORKDIR /app

# 🚨 FIX CRITIQUE : Désactiver le backend PIR de Paddle 3.0.0 pour éviter le bug "strides"
ENV FLAGS_enable_pir_api=0
ENV FLAGS_enable_pir_in_executor=0

# Installer les dépendances système (ajout de curl pour le healthcheck Coolify)
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

# Pré-télécharger le modèle Medium au build (le fix PIR est déjà actif via les ENV)
RUN python -c "from paddleocr import PaddleOCR; ocr = PaddleOCR(lang='fr', use_textline_orientation=True); print('Modele PP-OCRv6 Medium telecharge')"

# Exposer le port
EXPOSE 8100

# Healthcheck pour Coolify
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8100/sante || exit 1

# Lancer le serveur
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8100"]
