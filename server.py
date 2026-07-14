import os

# FIX CRITIQUE : Forcer ONNX Runtime AVANT tout import
os.environ["PADDLE_PDX_INFERENCE_BACKEND"] = "onnx"

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from paddleocr import PaddleOCR
import logging
import time
import io
import base64
import numpy as np
from PIL import Image

from parsers import (
    parser_document,
    verifier_correspondance,
    verifier_dates,
    determiner_action
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PP-OCRv6 Medium API - E-mariage", version="1.0.0")

# ── CORS : indispensable pour que emariage puisse appeler l'API ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def extraire_texte(img_array):
    """Lance l'OCR et retourne le texte brut + confiance moyenne."""
    ocr = get_ocr_instance()
    result = ocr.ocr(img_array, cls=True)

    if not result or not result[0]:
        return "", 0.0

    texte = " ".join(
        ligne[1][0] for ligne in result[0] if ligne[1][1] > 0.5
    )
    scores = [ligne[1][1] for ligne in result[0]]
    confiance_moy = sum(scores) / len(scores) if scores else 0
    return texte, confiance_moy


@app.get("/sante")
async def health_check():
    return {"status": "healthy", "model": "PP-OCRv6_medium", "backend": "onnx"}


# ── Endpoint principal utilisé par emariage ──
@app.post("/analyser-base64")
async def analyser_base64(data: dict):
    """
    Corps attendu :
    {
        "image": "base64...",
        "type_document": "CNI|PASSEPORT|EXTRAIT_NAISSANCE|AUTO",
        "donnees_declarees": {
            "nom": "KONE",
            "prenoms": "ALY ROGER",
            "date_naissance": "06/02/1996",
            "numero_piece": "CI0012345678"
        }
    }
    """
    start_time = time.time()
    try:
        img_b64 = data.get("image")
        if not img_b64:
            raise HTTPException(status_code=400, detail="Champ 'image' manquant")

        type_doc = data.get("type_document", "AUTO")
        declarees = data.get("donnees_declarees", {})

        img_bytes = base64.b64decode(img_b64)
        image = Image.open(io.BytesIO(img_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')

        if image.size[0] < 50 or image.size[1] < 50:
            return {
                "succes": False,
                "action": "REUPLOADER",
                "message": "Image trop petite ou corrompue"
            }

        img_array = np.array(image)
        texte, confiance_moy = extraire_texte(img_array)
        est_lisible = confiance_moy > 0.6

        if not texte:
            return {
                "succes": True,
                "texte_brut": "",
                "est_lisible": False,
                "infos_extraites": {},
                "correspondance": {},
                "validite_dates": {},
                "action": "REUPLOADER",
                "message": "Document illisible. Veuillez uploader une image plus claire."
            }

        infos = parser_document(texte, type_doc)
        infos["confiance_lecture"] = round(confiance_moy * 100, 1)

        correspondance = verifier_correspondance(infos, declarees)
        dates = verifier_dates(infos, type_doc)
        resultat = determiner_action(correspondance, dates, est_lisible)

        processing_time = round((time.time() - start_time) * 1000, 2)
        logger.info(f"Décision: {resultat['action']} en {processing_time}ms")

        return {
            "succes": True,
            "texte_brut": texte,
            "est_lisible": est_lisible,
            "confiance_moyenne": round(confiance_moy * 100, 1),
            "infos_extraites": infos,
            "correspondance": correspondance,
            "validite_dates": dates,
            "action": resultat["action"],
            "message": resultat["message"],
            "processing_time_ms": processing_time
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur analyse: {str(e)}")
        return {
            "succes": False,
            "erreur": str(e),
            "action": "REUPLOADER",
            "message": "Une erreur est survenue lors de l'analyse. Veuillez réessayer."
        }


# ── Endpoint de test brut (utile pour diagnostiquer avec curl) ──
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
