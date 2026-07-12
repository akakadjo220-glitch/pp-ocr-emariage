import re
import unicodedata
from datetime import datetime, timedelta

def normaliser_nom(texte: str) -> str:
    """
    Normalise un nom ivoirien pour comparaison.
    Tolerant : accents, casse, apostrophes, tirets.
    """
    if not texte:
        return ""
    # Supprimer accents
    texte = unicodedata.normalize('NFD', texte)
    texte = ''.join(
        c for c in texte
        if unicodedata.category(c) != 'Mn'
    )
    # Majuscules
    texte = texte.upper()
    # Supprimer apostrophes, tirets, espaces
    texte = re.sub(r"['\-\s]", "", texte)
    # Supprimer mentions maritales
    for mention in [
        'EPOUSE', 'NEE', 'VEUVE',
        'VE', 'DIVORCE', 'NE'
    ]:
        texte = texte.replace(mention, "")
    return texte.strip()

def parser_document(texte: str, type_doc: str) -> dict:
    """
    Extraire les informations d'un document
    à partir du texte OCR brut.
    """
    infos = {
        "type_detecte": "INCONNU",
        "nom": None,
        "prenoms": None,
        "date_naissance": None,
        "lieu_naissance": None,
        "numero_piece": None,
        "date_expiration": None,
        "date_delivrance": None,
        "lieu_naissance_etranger": False,
        "confiance_lecture": 0
    }

    t = texte.upper()

    # ── Détecter type de document ──
    if any(x in t for x in [
        "CARTE NATIONALE", "CNI",
        "IDENTITE", "IVOIRIEN"
    ]):
        infos["type_detecte"] = "CNI"
    elif "PASSEPORT" in t:
        infos["type_detecte"] = "PASSEPORT"
    elif any(x in t for x in [
        "NAISSANCE", "EXTRAIT",
        "ACTE", "ETAT CIVIL"
    ]):
        infos["type_detecte"] = "EXTRAIT_NAISSANCE"

    # ── Numéro CNI ivoirien (CI + 10 chiffres) ──
    cni = re.search(r'\bCI\d{10}\b', t)
    if cni:
        infos["numero_piece"] = cni.group()

    # ── Numéro Passeport (lettre(s) + chiffres) ──
    if not cni:
        psp = re.search(r'\b[A-Z]{1,2}\d{7,9}\b', t)
        if psp:
            infos["numero_piece"] = psp.group()

    # ── Extraire toutes les dates ──
    toutes_dates = re.findall(
        r'\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\b',
        texte
    )

    # ── Date de délivrance (extrait naissance) ──
    patterns_delivrance = [
        r'D[EÉ]LIVR[EÉ]\s+LE\s*[:\s]*([\d/\-\.]{10})',
        r'FAIT\s+[AÀ]\s+\w+\s*[,\s]+LE\s*([\d/\-\.]{10})',
        r'CERTIFI[EÉ]\s+CONFORME\s+LE\s*([\d/\-\.]{10})',
        r'LE\s+PRESENT\s+EXTRAIT\s+EST\s+D[EÉ]LIVR[EÉ]\s+LE\s*([\d/\-\.]{10})'
    ]
    for pattern in patterns_delivrance:
        m = re.search(pattern, t)
        if m:
            infos["date_delivrance"] = \
                m.group(1).replace('-', '/').replace('.', '/')
            break

    # ── Date expiration (CNI/Passeport) ──
    patterns_expiration = [
        r'(?:EXPIRE|EXPIRATION|VALABLE)\s+(?:LE\s+|JUSQU[^\d]*)?([\d/\-\.]{10})',
        r'DATE\s+D[\'E]EXPIRATION\s*[:\s]*([\d/\-\.]{10})',
        r'VALID\s+UNTIL\s*([\d/\-\.]{10})'
    ]
    for pattern in patterns_expiration:
        m = re.search(pattern, t)
        if m:
            infos["date_expiration"] = \
                m.group(1).replace('-', '/').replace('.', '/')
            break

    # ── Détecter naissance à l'étranger ──
    pays_etrangers = [
        "FRANCE", "MALI", "SENEGAL", "BURKINA",
        "GHANA", "GUINEE", "NIGERIA", "NIGER",
        "TOGO", "BENIN", "CAMEROUN", "CONGO",
        "GABON", "LIBERIA", "MAURITANIE"
    ]
    for pays in pays_etrangers:
        if pays in t:
            infos["lieu_naissance_etranger"] = True
            break

    return infos

def verifier_correspondance(
    infos: dict,
    declarees: dict
) -> dict:
    """
    Comparer les infos extraites du document
    avec les données déclarées à l'inscription.
    """
    r = {
        "nom_ok": False,
        "prenoms_ok": False,
        "date_naissance_ok": False,
        "numero_piece_ok": False,
        "score_global": 0,
        "details": {}
    }

    if not declarees:
        return r

    # Nom (tolérant)
    if infos.get("nom") and declarees.get("nom"):
        nom_doc = normaliser_nom(infos["nom"])
        nom_dec = normaliser_nom(declarees["nom"])
        r["nom_ok"] = nom_doc == nom_dec
        r["details"]["nom"] = {
            "document": nom_doc,
            "declare": nom_dec
        }

    # Prénoms (tolérant)
    if infos.get("prenoms") and declarees.get("prenoms"):
        pre_doc = normaliser_nom(infos["prenoms"])
        pre_dec = normaliser_nom(declarees["prenoms"])
        r["prenoms_ok"] = pre_doc == pre_dec
        r["details"]["prenoms"] = {
            "document": pre_doc,
            "declare": pre_dec
        }

    # Date naissance (STRICTE)
    if infos.get("date_naissance") and \
       declarees.get("date_naissance"):
        d_doc = infos["date_naissance"]\
            .replace("-", "/").replace(".", "/")
        d_dec = declarees["date_naissance"]\
            .replace("-", "/").replace(".", "/")
        r["date_naissance_ok"] = d_doc == d_dec
        r["details"]["date_naissance"] = {
            "document": d_doc,
            "declare": d_dec
        }

    # Numéro pièce (STRICTE)
    if infos.get("numero_piece") and \
       declarees.get("numero_piece"):
        n_doc = infos["numero_piece"].upper().strip()
        n_dec = declarees["numero_piece"].upper().strip()
        r["numero_piece_ok"] = n_doc == n_dec
        r["details"]["numero_piece"] = {
            "document": n_doc,
            "declare": n_dec
        }

    # Score global
    checks = [
        r["nom_ok"], r["prenoms_ok"],
        r["date_naissance_ok"],
        r["numero_piece_ok"]
    ]
    r["score_global"] = \
        sum(checks) / len(checks) * 100

    return r

def verifier_dates(infos: dict, type_doc: str) -> dict:
    """
    Vérifier la validité des dates du document.
    """
    maintenant = datetime.now()
    r = {
        "piece_expiree": False,
        "extrait_perime": False,
        "message": None,
        "date_actuelle": maintenant\
            .strftime("%d/%m/%Y")
    }

    # Vérifier expiration CNI/Passeport
    if infos.get("date_expiration"):
        try:
            exp = datetime.strptime(
                infos["date_expiration"],
                "%d/%m/%Y"
            )
            if exp < maintenant:
                r["piece_expiree"] = True
                r["message"] = (
                    f"Votre pièce d'identité est "
                    f"expirée depuis le "
                    f"{infos['date_expiration']}. "
                    f"Veuillez fournir une pièce valide."
                )
        except ValueError:
            pass

    # Vérifier validité extrait naissance
    if type_doc == "EXTRAIT_NAISSANCE" and \
       infos.get("date_delivrance"):
        try:
            deliv = datetime.strptime(
                infos["date_delivrance"],
                "%d/%m/%Y"
            )
            est_etranger = infos.get(
                "lieu_naissance_etranger", False
            )
            jours = 180 if est_etranger else 90
            mois = 6 if est_etranger else 3
            limite = maintenant - timedelta(days=jours)

            if deliv < limite:
                r["extrait_perime"] = True
                r["message"] = (
                    f"Extrait de naissance périmé. "
                    f"Il doit dater de moins de "
                    f"{mois} mois. "
                    f"Délivré le "
                    f"{infos['date_delivrance']}. "
                    f"Veuillez en obtenir un nouveau "
                    f"auprès de votre mairie d'état civil."
                )
        except ValueError:
            pass

    return r

def determiner_action(
    correspondance: dict,
    dates: dict,
    est_lisible: bool = True
) -> dict:
    """
    Déterminer l'action finale basée sur
    tous les contrôles.
    """
    # Document illisible
    if not est_lisible:
        return {
            "action": "REUPLOADER",
            "message": (
                "Votre document est illisible. "
                "Veuillez prendre une photo plus "
                "nette, bien éclairée et bien cadrée."
            )
        }

    # Dates invalides → REJETER
    if dates["piece_expiree"] or \
       dates["extrait_perime"]:
        return {
            "action": "REJETER",
            "message": dates["message"]
        }

    score = correspondance.get("score_global", 0)
    date_ok = correspondance.get("date_naissance_ok")
    piece_ok = correspondance.get("numero_piece_ok")

    # Correspondance parfaite
    if score >= 75 and date_ok and piece_ok:
        return {
            "action": "ACCEPTER",
            "message": "Document validé avec succès ✅"
        }

    # Doute → vérification manuelle
    if score >= 50:
        return {
            "action": "VERIFIER_MANUELLEMENT",
            "message": (
                "Des informations du document "
                "ne correspondent pas exactement "
                "aux données déclarées. "
                "Vérification manuelle requise."
            )
        }

    # Échec → REJETER
    return {
        "action": "REJETER",
        "message": (
            "Les informations du document "
            "ne correspondent pas aux données "
            "que vous avez déclarées. "
            "Vérifiez vos informations ou "
            "contactez la mairie."
        )
    }