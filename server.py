import os
import io
import json
import time
import base64
import logging
import requests
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from parsers import (
    parser_document,
    verifier_correspondance,
    verifier_dates,
    determiner_action,
    verifier_residence_couple
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OCR API - E-mariage (AIStudio PaddleOCR)", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

AISTUDIO_TOKEN = os.environ.get("AISTUDIO_TOKEN", "")
JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"

if not AISTUDIO_TOKEN:
    logger.warning("AISTUDIO_TOKEN non defini ! A configurer dans Coolify.")


def choisir_modele(type_doc: str) -> str:
    if type_doc in ("CNI", "PASSEPORT"):
        return "PP-OCRv6"
    if type_doc in (
        "EXTRAIT_NAISSANCE", "CERTIFICAT_RESIDENCE", "CERTIFICAT_PRESENCE_CORPS"
    ):
        return "PP-StructureV3"
    return "PP-OCRv6"


def soumettre_job(image_bytes: bytes, model: str) -> str:
    headers = {"Authorization": f"bearer {AISTUDIO_TOKEN}"}
    optional_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
    }
    if model == "PP-OCRv6":
        optional_payload["useTextlineOrientation"] = False
    else:
        optional_payload["useChartRecognition"] = False

    data = {"model": model, "optionalPayload": json.dumps(optional_payload)}
    files = {"file": ("document.jpg", image_bytes, "image/jpeg")}

    resp = requests.post(JOB_URL, headers=headers, data=data, files=files, timeout=30)

    if resp.status_code == 429:
        raise RuntimeError("QUOTA_DEPASSE")
    if resp.status_code in (401, 403):
        raise RuntimeError("TOKEN_EXPIRE")

    resp.raise_for_status()
    return resp.json()["data"]["jobId"]


def attendre_job(job_id: str, timeout_max: int = 45) -> dict:
    headers = {"Authorization": f"bearer {AISTUDIO_TOKEN}"}
    debut = time.time()

    while time.time() - debut < timeout_max:
        resp = requests.get(f"{JOB_URL}/{job_id}", headers=headers, timeout=15)
        resp.raise_for_status()
        payload = resp.json()["data"]
        state = payload["state"]

        if state == "done":
            return {"succes": True, "url": payload["resultUrl"]["jsonUrl"]}
        if state == "failed":
            return {"succes": False, "erreur": payload.get("errorMsg", "Erreur inconnue")}

        time.sleep(2)

    return {"succes": False, "erreur": "Timeout: traitement trop long"}


def extraire_texte_ocrv6(resultat_json: dict):
    textes, scores = [], []
    for res in resultat_json.get("ocrResults", []):
        pruned = res.get("prunedResult", {})
        textes.extend(pruned.get("rec_texts", []))
        scores.extend(pruned.get("rec_scores", []))

    texte = " ".join(textes)
    confiance = sum(scores) / len(scores) if scores else 0.0
    return texte, confiance


def extraire_texte_structurev3(resultat_json: dict):
    textes = []
    for res in resultat_json.get("layoutParsingResults", []):
        textes.append(res.get("markdown", {}).get("text", ""))

    texte_md = "\n".join(textes)
    texte_nettoye = texte_md.replace("|", " ").replace("#", " ").replace("*", " ")
    confiance = 0.85 if len(texte_nettoye.strip()) > 20 else 0.3
    return texte_nettoye, confiance


def traiter_document(image_bytes: bytes, type_doc: str):
    model = choisir_modele(type_doc)
    job_id = soumettre_job(image_bytes, model)
    resultat_job = attendre_job(job_id)

    if not resultat_job["succes"]:
        raise RuntimeError(resultat_job["erreur"])

    jsonl_resp = requests.get(resultat_job["url"], timeout=30)
    jsonl_resp.raise_for_status()

    lignes = [l for l in jsonl_resp.text.strip().split("\n") if l.strip()]
    if not lignes:
        return "", 0.0

    resultat_json = json.loads(lignes[0])["result"]

    if model == "PP-OCRv6":
        return extraire_texte_ocrv6(resultat_json)
    return extraire_texte_structurev3(resultat_json)


@app.get("/sante")
async def health_check():
    return {
        "status": "healthy",
        "backend": "AIStudio PaddleOCR (cloud)",
        "modeles": ["PP-OCRv6", "PP-StructureV3"],
        "token_configure": bool(AISTUDIO_TOKEN)
    }


@app.post("/analyser-base64")
async def analyser_base64(data: dict):
    """
    Corps attendu :
    {
        "image": "base64...",
        "type_document": "CNI|PASSEPORT|EXTRAIT_NAISSANCE|CERTIFICAT_RESIDENCE|CERTIFICAT_PRESENCE_CORPS|AUTO",
        "donnees_declarees": {
            "nom": "...", "prenoms": "...",
            "date_naissance": "JJ/MM/AAAA", "numero_piece": "..."
        },
        "date_mariage": "JJ/MM/AAAA"   <-- OPTIONNEL
        (si la date de mariage est deja connue/choisie au moment
        de cet upload, la fournir permet de verifier directement
        la validite de l'extrait de naissance contre la VRAIE date
        du mariage plutot que contre la date du jour. Si absente,
        la verification se fait contre aujourd'hui et devra etre
        RE-CONFIRMEE via /revalider-date-mariage une fois la date
        choisie - voir plus bas.)
    }
    """
    start_time = time.time()
    try:
        img_b64 = data.get("image")
        if not img_b64:
            raise HTTPException(status_code=400, detail="Champ 'image' manquant")

        type_doc = data.get("type_document", "AUTO")
        declarees = data.get("donnees_declarees", {})
        date_mariage = data.get("date_mariage")

        img_bytes = base64.b64decode(img_b64)
        image = Image.open(io.BytesIO(img_bytes))
        if image.mode != "RGB":
            image = image.convert("RGB")
        if image.size[0] < 50 or image.size[1] < 50:
            return {"succes": False, "action": "REUPLOADER", "message": "Image trop petite ou corrompue"}

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=92)
        img_bytes_norm = buffer.getvalue()

        try:
            texte, confiance_moy = traiter_document(img_bytes_norm, type_doc)
        except RuntimeError as e:
            if str(e) == "QUOTA_DEPASSE":
                logger.error("Quota AIStudio depasse (429)")
                return {"succes": False, "action": "VERIFIER_MANUELLEMENT",
                        "message": "Service sature, nouvelle tentative dans un instant."}
            if str(e) == "TOKEN_EXPIRE":
                logger.error("Token AIStudio expire/invalide")
                return {"succes": False, "action": "VERIFIER_MANUELLEMENT",
                        "message": "Erreur de configuration du service. Equipe technique alertee."}
            raise

        est_lisible = confiance_moy > 0.5

        if not texte.strip():
            return {
                "succes": True, "texte_brut": "", "est_lisible": False,
                "infos_extraites": {}, "correspondance": {}, "validite_dates": {},
                "action": "REUPLOADER",
                "message": "Document illisible. Veuillez uploader une image plus claire."
            }

        infos = parser_document(texte, type_doc)
        infos["confiance_lecture"] = round(confiance_moy * 100, 1)
        correspondance = verifier_correspondance(infos, declarees)
        dates = verifier_dates(infos, type_doc, date_mariage)
        resultat = determiner_action(correspondance, dates, est_lisible)

        processing_time = round((time.time() - start_time) * 1000, 2)
        logger.info(f"Decision: {resultat['action']} en {processing_time}ms")

        return {
            "succes": True,
            "texte_brut": texte,
            "est_lisible": est_lisible,
            "confiance_moyenne": round(confiance_moy * 100, 1),
            "modele_utilise": choisir_modele(type_doc),
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
        return {"succes": False, "erreur": str(e), "action": "REUPLOADER",
                "message": "Une erreur est survenue. Veuillez reessayer."}


@app.post("/revalider-date-mariage")
async def revalider_date_mariage(data: dict):
    """
    A appeler quand la date du mariage est choisie/confirmee
    (Phase 3-4), pour revalider l'extrait de naissance deja
    analyse contre la VRAIE date du mariage. Ne refait PAS
    d'OCR (rapide, pas d'appel cloud AIStudio).

    Corps attendu :
    {
        "infos_extraites": {...deja renvoye par /analyser-base64...},
        "type_document": "EXTRAIT_NAISSANCE",
        "date_mariage": "JJ/MM/AAAA"
    }
    """
    infos = data.get("infos_extraites")
    type_doc = data.get("type_document")
    date_mariage = data.get("date_mariage")

    if not infos or not type_doc or not date_mariage:
        raise HTTPException(
            status_code=400,
            detail="infos_extraites, type_document et date_mariage sont requis"
        )

    dates = verifier_dates(infos, type_doc, date_mariage)
    resultat = determiner_action({"score_global": 100, "date_naissance_ok": True,
                                   "numero_piece_ok": True, "details": {}}, dates, True)

    return {
        "validite_dates": dates,
        "action": resultat["action"],
        "message": resultat["message"] if dates.get("extrait_perime") else (
            "Document toujours valide a la date du mariage choisie."
        )
    }


@app.post("/verifier-residence-couple")
async def verifier_residence(data: dict):
    """
    Corps attendu :
    {
        "infos_epoux": {...infos_extraites du certificat epoux...},
        "infos_epouse": {...infos_extraites du certificat epouse...}
    }
    """
    infos_epoux = data.get("infos_epoux", {})
    infos_epouse = data.get("infos_epouse", {})

    if not infos_epoux or not infos_epouse:
        raise HTTPException(status_code=400, detail="infos_epoux et infos_epouse sont requis")

    return verifier_residence_couple(infos_epoux, infos_epouse)


@app.post("/ocr")
async def ocr_test(file: UploadFile = File(...), type_document: str = "CNI"):
    try:
        contents = await file.read()
        texte, confiance = traiter_document(contents, type_document)
        return {
            "status": "success",
            "modele_utilise": choisir_modele(type_document),
            "texte": texte,
            "confiance_moyenne": round(confiance * 100, 1)
        }
    except Exception as e:
        logger.error(f"Erreur OCR test: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
