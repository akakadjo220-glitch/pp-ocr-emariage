import os
# 🚨 FIX CRITIQUE : Désactiver le backend PIR de Paddle 3.0.0 pour éviter le bug "strides"
# DOIT être exécuté AVANT d'importer PaddleOCR
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from paddleocr import PaddleOCR
import logging
import time
import io
import numpy as np
from PIL import Image

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PP-OCRv6 Medium API - E-mariage", version="1.0.0")

# Initialisation de PaddleOCR avec PP-OCRv6_medium
logger.info("Chargement PP-OCRv6 Medium 34.5M...")
try:
    ocr = PaddleOCR(
        lang='fr',
        use_textline_orientation=True
    )
    logger.info("PP-OCRv6 Medium chargé avec succès ✅")
except Exception as e:
    logger.error(f"Erreur de chargement: {e}")
    raise

@app.get("/sante")
async def health_check():
    """Endpoint pour le healthcheck de Coolify"""
    return {"status": "healthy", "model": "PP-OCRv6_medium"}

@app.post("/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    """Endpoint principal pour l'OCR via upload de fichier"""
    start_time = time.time()
    try:
        # Lire l'image uploadée
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        
        # Convertir en RGB pour éviter les erreurs (RGBA, niveaux de gris, etc.)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Convertir en array numpy pour PaddleOCR
        img_array = np.array(image)

        # Exécuter l'OCR
        result = ocr.ocr(img_array, cls=True)

        processing_time = time.time() - start_time

        # Formater la réponse
        texts = []
        if result and result[0]:
            for line in result[0]:
                texts.append({
                    "text": line[1][0],
                    "confidence": float(line[1][1]),
                    "box": line[0]
                })

        return {
            "status": "success",
            "processing_time_ms": round(processing_time * 1000, 2),
            "results": texts
        }

    except Exception as e:
        logger.error(f"Erreur OCR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ocr-url")
async def ocr_from_url(url: str):
    """Endpoint optionnel pour tester avec une URL d'image"""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            img_array = np.array(image)
            result = ocr.ocr(img_array, cls=True)
            
            texts = []
            if result and result[0]:
                for line in result[0]:
                    texts.append({
                        "text": line[1][0],
                        "confidence": float(line[1][1]),
                        "box": line[0]
                    })
            
            return {"status": "success", "results": texts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
