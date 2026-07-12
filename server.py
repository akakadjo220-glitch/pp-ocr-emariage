import os

# FIX CRITIQUE : Forcer ONNX Runtime AVANT tout import
os.environ["PADDLE_PDX_INFERENCE_BACKEND"] = "onnx"

from fastapi import FastAPI, HTTPException, UploadFile, File
from paddleocr import PaddleOCR
import logging
import time
import io
import numpy as np
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PP-OCRv6 Medium API - E-mariage", version="1.0.0")

# Variable globale pour lazy loading
_ocr_instance = None

def get_ocr_instance():
    global _ocr_instance
    if _ocr_instance is None:
        logger.info("Initialisation PaddleOCR avec backend ONNX...")
        try:
            _ocr_instance = PaddleOCR(
                lang='fr',
                use_textline_orientation=True
            )
            logger.info("PP-OCRv6 Medium chargé via ONNX ✅")
        except Exception as e:
            logger.error(f"Erreur: {e}")
            raise
    return _ocr_instance

@app.get("/sante")
async def health_check():
    return {"status": "healthy", "model": "PP-OCRv6_medium", "backend": "onnx"}

@app.post("/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    start_time = time.time()
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        img_array = np.array(image)
        
        ocr = get_ocr_instance()
        result = ocr.ocr(img_array, cls=True)
        
        processing_time = time.time() - start_time
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
