from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from paddleocr import PaddleOCR
from PIL import Image
import base64
import io
import logging
from parsers import (
    parser_document,
    verifier_correspondance,
    verifier_dates,
    determiner_action
)

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PP-OCRv6 Service - I Mariage",
    description="Service OCR pour la Mairie de Cocody",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Initialiser PP-OCRv6 Medium UNE SEULE FOIS ──
logger.info("Chargement PP-OCRv6 Medium 34.5M...")
ocr = PaddleOCR(
    use_textline_orientation=True,
    lang='fr',
    
)
logger.info("PP-OCRv6 Medium chargé avec succès ✅")


@app.get("/sante")
def sante():
    """Endpoint de santé pour Coolify."""
    return {
        "statut": "ok",
        "modele": "PP-OCRv6 Medium 34.5M",
        "version": "3.7.0",
        "service": "I Mariage - Mairie de Cocody"
    }


@app.post("/analyser-base64")
async def analyser_base64(data: dict):
    """
    Analyser un document encodé en base64.
    Corps attendu :
    {
        "image": "base64...",
        "type_document": "CNI|PASSEPORT|EXTRAIT_NAISSANCE|AUTO",
        "donnees_declarees": {
            "nom": "KONÉ",
            "prenoms": "ALY ROGER",
            "date_naissance": "06/02/1996",
            "numero_piece": "CI0012345678"
        }
    }
    """
    try:
        # Valider les données reçues
        img_b64 = data.get("image")
        if not img_b64:
            raise HTTPException(
                status_code=400,
                detail="Champ 'image' manquant"
            )

        type_doc = data.get("type_document", "AUTO")
        declarees = data.get("donnees_declarees", {})

        # Décoder l'image
        img_bytes = base64.b64decode(img_b64)
        img = Image.open(io.BytesIO(img_bytes))

        # Vérifier que l'image est lisible
        if img.size[0] < 50 or img.size[1] < 50:
            return {
                "succes": False,
                "action": "REUPLOADER",
                "message": "Image trop petite ou corrompue"
            }

        # Lancer PP-OCR
        logger.info(
            f"Analyse document type: {type_doc}"
        )
        result = ocr.ocr(img, cls=True)

        # Extraire le texte
        if not result or not result[0]:
            return {
                "succes": True,
                "texte_brut": "",
                "est_lisible": False,
                "infos_extraites": {},
                "correspondance": {},
                "validite_dates": {},
                "action": "REUPLOADER",
                "message": (
                    "Document illisible. "
                    "Veuillez uploader une image "
                    "plus claire."
                )
            }

        # Assembler le texte complet
        texte = " ".join(
            ligne[1][0]
            for ligne in result[0]
            if ligne[1][1] > 0.5  # Confiance > 50%
        )

        # Score de lisibilité global
        scores = [
            ligne[1][1]
            for ligne in result[0]
        ]
        confiance_moy = sum(scores) / len(scores) \
            if scores else 0
        est_lisible = confiance_moy > 0.6

        logger.info(
            f"Texte extrait ({len(texte)} chars), "
            f"confiance: {confiance_moy:.2f}"
        )

        # Parser les informations
        infos = parser_document(texte, type_doc)
        infos["confiance_lecture"] = round(
            confiance_moy * 100, 1
        )

        # Vérifier correspondance
        correspondance = verifier_correspondance(
            infos, declarees
        )

        # Vérifier dates
        dates = verifier_dates(infos, type_doc)

        # Déterminer action finale
        resultat = determiner_action(
            correspondance, dates, est_lisible
        )

        logger.info(
            f"Décision: {resultat['action']}"
        )

        return {
            "succes": True,
            "texte_brut": texte,
            "est_lisible": est_lisible,
            "confiance_moyenne": round(
                confiance_moy * 100, 1
            ),
            "infos_extraites": infos,
            "correspondance": correspondance,
            "validite_dates": dates,
            "action": resultat["action"],
            "message": resultat["message"]
        }

    except Exception as e:
        logger.error(f"Erreur analyse: {str(e)}")
        return {
            "succes": False,
            "erreur": str(e),
            "action": "REUPLOADER",
            "message": (
                "Une erreur est survenue lors "
                "de l'analyse. Veuillez réessayer."
            )
        }


@app.post("/tester")
async def tester():
    """
    Test rapide du service avec une image synthétique.
    """
    try:
        # Créer une image test simple
        img = Image.new('RGB', (200, 50), color='white')
        result = ocr.ocr(img, cls=True)
        return {
            "statut": "ok",
            "message": "Service PP-OCR fonctionnel ✅"
        }
    except Exception as e:
        return {
            "statut": "erreur",
            "message": str(e)
        }
