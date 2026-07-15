import re
import unicodedata
import codecs
from datetime import datetime, timedelta

# ==============================================================================
# FONCTIONS UTILITAIRES
# ==============================================================================

def decoder_texte_brut(texte: str) -> str:
    """Décode les séquences Unicode échappées (\u0027 -> ', \u00c9 -> É, etc.)"""
    if not texte:
        return ""
    try:
        # Décodage standard des séquences Unicode
        texte = codecs.decode(texte, 'unicode_escape')
        # Nettoyage supplémentaire de sécurité pour les artefacts courants
        texte = texte.replace('\u0027', "'") \
                     .replace('\u003c', '<') \
                     .replace('\u003e', '>') \
                     .replace('\u00c9', 'É') \
                     .replace('\u00e9', 'é') \
                     .replace('\u00c8', 'È') \
                     .replace('\u00e8', 'è') \
                     .replace('\u00ca', 'Ê') \
                     .replace('\u00ea', 'ê') \
                     .replace('\u00c0', 'À') \
                     .replace('\u00e0', 'à')
        return texte
    except Exception:
        return texte

def normaliser_nom(texte: str) -> str:
    """Normalise un nom ivoirien pour comparaison (tolérant aux accents, apostrophes, etc.)"""
    if not texte:
        return ""
    # 1. Supprimer les accents
    texte = unicodedata.normalize('NFD', texte)
    texte = ''.join(c for c in texte if unicodedata.category(c) != 'Mn')
    # 2. Mettre en majuscules
    texte = texte.upper()
    # 3. Supprimer apostrophes, tirets et espaces
    texte = re.sub(r"['\-\s]", "", texte)
    # 4. Supprimer les mentions matrimoniales parasites
    for mention in ['EPOUSE', 'NEE', 'VEUVE', 'VE', 'DIVORCE', 'NE']:
        texte = texte.replace(mention, "")
    return texte.strip()

def _parser_date(date_str: str):
    """Parse une date JJ/MM/AAAA, JJ-MM-AAAA ou JJ.MM.AAAA en toute sécurité."""
    if not date_str:
        return None
    try:
        date_normalisee = date_str.replace("-", "/").replace(".", "/")
        return datetime.strptime(date_normalisee, "%d/%m/%Y")
    except ValueError:
        return None

# ==============================================================================
# CONSTANTES
# ==============================================================================

COMMUNES_ABIDJAN = [
    "COCODY", "ABOBO", "ADJAME", "ATTECOUBE", "PLATEAU",
    "KOUMASSI", "MARCORY", "PORT-BOUET", "PORT BOUET",
    "TREICHVILLE", "YOPOUGON", "ANYAMA", "BINGERVILLE", "SONGON"
]

PAYS_ETRANGERS = [
    "FRANCE", "MALI", "SENEGAL", "BURKINA", "GHANA", "GUINEE",
    "NIGERIA", "NIGER", "TOGO", "BENIN", "CAMEROUN", "CONGO",
    "GABON", "LIBERIA", "MAURITANIE"
]

# ==============================================================================
# FONCTIONS PRINCIPALES D'ANALYSE
# ==============================================================================

def parser_document(texte_brut: str, type_doc: str) -> dict:
    """Extrait les informations d'un document à partir du texte OCR brut."""
    # 1. DÉCODER le texte avant toute analyse regex
    texte = decoder_texte_brut(texte_brut)
    t = texte.upper()

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
        "commune_residence": None,
        "reside_cocody": False,
        "confiance_lecture": 0
    }

    # --- Détection du type de document ---
    if any(x in t for x in ["CARTE NATIONALE", "CNI", "IDENTITE", "IVOIRIEN"]):
        infos["type_detecte"] = "CNI"
    elif "PASSEPORT" in t:
        infos["type_detecte"] = "PASSEPORT"
    elif any(x in t for x in ["NAISSANCE", "EXTRAIT", "ACTE", "ETAT CIVIL"]) and "RESIDENCE" not in t:
        infos["type_detecte"] = "EXTRAIT_NAISSANCE"
    elif any(x in t for x in ["PRESENCE AU CORPS", "PRESENCE A CORPS", "CERTIFICAT DE PRESENCE"]):
        infos["type_detecte"] = "CERTIFICAT_PRESENCE_CORPS"
    elif any(x in t for x in ["CERTIFICAT DE RESIDENCE", "ATTESTATION DE RESIDENCE", "CERTIFICAT DE DOMICILE", "RESIDENCE"]):
        infos["type_detecte"] = "CERTIFICAT_RESIDENCE"

    # --- Extraction Numéro de pièce ---
    cni_match = re.search(r'\bCI\d{10}\b', t)
    if cni_match:
        infos["numero_piece"] = cni_match.group()
    else:
        psp_match = re.search(r'\b[A-Z]{1,2}\d{7,9}\b', t)
        if psp_match:
            infos["numero_piece"] = psp_match.group()

    # --- Extraction Date de délivrance ---
    patterns_delivrance = [
        r'D[EÉ]LIVR[EÉ]\s+LE\s*[:\s]*([\d/\-\.]{10})',
        r'FAIT\s+[AÀ]\s+\w+\s*[, \s]+LE\s*([\d/\-\.]{10})',
        r'CERTIFI[EÉ]\s+CONFORME\s+LE\s*([\d/\-\.]{10})',
        r'LE\s+PRESENT\s+EXTRAIT\s+EST\s+D[EÉ]LIVR[EÉ]\s+LE\s*([\d/\-\.]{10})',
        r'CERTIFIE\s+LE\s*[:\s]*([\d/\-\.]{10})',
        r'ABIDJAN\s*[, \s]+LE\s*([\d/\-\.]{10})'
    ]
    for pattern in patterns_delivrance:
        m = re.search(pattern, t)
        if m:
            infos["date_delivrance"] = m.group(1).replace('-', '/').replace('.', '/')
            break

    # --- Extraction Date d'expiration ---
    patterns_expiration = [
        r'(?:EXPIRE|EXPIRATION|VALABLE)\s+(?:LE\s+|JUSQU[^\d]*)?([\d/\-\.]{10})',
        r'DATE\s+D[\'E]EXPIRATION\s*[:\s]*([\d/\-\.]{10})',
        r'VALID\s+UNTIL\s*([\d/\-\.]{10})'
    ]
    for pattern in patterns_expiration:
        m = re.search(pattern, t)
        if m:
            infos["date_expiration"] = m.group(1).replace('-', '/').replace('.', '/')
            break

    # --- Détection naissance à l'étranger ---
    for pays in PAYS_ETRANGERS:
        if pays in t:
            infos["lieu_naissance_etranger"] = True
            break

    # --- Détection commune de résidence ---
    if infos["type_detecte"] in ("CERTIFICAT_RESIDENCE", "CERTIFICAT_PRESENCE_CORPS"):
        for commune in COMMUNES_ABIDJAN:
            if commune in t:
                infos["commune_residence"] = commune
                if commune == "COCODY":
                    infos["reside_cocody"] = True
                break

    return infos


def verifier_correspondance(infos: dict, declarees: dict) -> dict:
    """Compare les infos extraites du document avec les données déclarées."""
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
        r["nom_ok"] = (nom_doc == nom_dec)
        r["details"]["nom"] = {"document": nom_doc, "declare": nom_dec}

    # Prénoms (tolérant)
    if infos.get("prenoms") and declarees.get("prenoms"):
        pre_doc = normaliser_nom(infos["prenoms"])
        pre_dec = normaliser_nom(declarees["prenoms"])
        r["prenoms_ok"] = (pre_doc == pre_dec)
        r["details"]["prenoms"] = {"document": pre_doc, "declare": pre_dec}

    # Date de naissance (STRICTE)
    if infos.get("date_naissance") and declarees.get("date_naissance"):
        d_doc = infos["date_naissance"].replace("-", "/").replace(".", "/")
        d_dec = declarees["date_naissance"].replace("-", "/").replace(".", "/")
        r["date_naissance_ok"] = (d_doc == d_dec)
        r["details"]["date_naissance"] = {"document": d_doc, "declare": d_dec}

    # Numéro de pièce (STRICTE)
    if infos.get("numero_piece") and declarees.get("numero_piece"):
        n_doc = infos["numero_piece"].upper().strip()
        n_dec = declarees["numero_piece"].upper().strip()
        r["numero_piece_ok"] = (n_doc == n_dec)
        r["details"]["numero_piece"] = {"document": n_doc, "declare": n_dec}

    # Calcul du score global
    # Pour les certificats de résidence/présence, on ne vérifie que le nom et prénoms
    if infos.get("type_detecte") in ("CERTIFICAT_RESIDENCE", "CERTIFICAT_PRESENCE_CORPS"):
        checks = [r["nom_ok"], r["prenoms_ok"]]
    else:
        checks = [r["nom_ok"], r["prenoms_ok"], r["date_naissance_ok"], r["numero_piece_ok"]]

    r["score_global"] = (sum(checks) / len(checks) * 100) if checks else 0
    return r


def verifier_dates(infos: dict, type_doc: str, date_mariage: str = None) -> dict:
    """
    Vérifie la validité des dates du document.
    Si date_mariage est fournie, l'extrait de naissance est vérifié par rapport à cette date.
    Sinon, il est vérifié par rapport à la date du jour (vérification provisoire à l'upload).
    """
    aujourdhui = datetime.now()
    reference_extrait = _parser_date(date_mariage) or aujourdhui

    r = {
        "piece_expiree": False,
        "extrait_perime": False,
        "residence_perimee": False,
        "reference_utilisee": "date_mariage" if date_mariage else "date_jour",
        "message": None,
        "date_actuelle": aujourdhui.strftime("%d/%m/%Y")
    }

    # 1. CNI / Passeport (toujours vérifié par rapport à aujourd'hui)
    exp = _parser_date(infos.get("date_expiration"))
    if exp and exp < aujourdhui:
        r["piece_expiree"] = True
        r["message"] = f"Votre pièce d'identité est expirée depuis le {infos['date_expiration']}. Veuillez fournir une pièce valide."

    # 2. Extrait de naissance : < 3 mois (CI) ou < 6 mois (Étranger) À LA DATE DU MARIAGE
    if type_doc == "EXTRAIT_NAISSANCE":
        deliv = _parser_date(infos.get("date_delivrance"))
        if deliv:
            est_etranger = infos.get("lieu_naissance_etranger", False)
            jours = 180 if est_etranger else 90
            mois = 6 if est_etranger else 3
            limite = reference_extrait - timedelta(days=jours)

            if deliv < limite:
                r["extrait_perime"] = True
                if date_mariage:
                    r["message"] = (f"Extrait de naissance périmé à la date du mariage prévue ({date_mariage}). "
                                    f"Il doit dater de moins de {mois} mois par rapport à la date du mariage. "
                                    f"Délivré le {infos['date_delivrance']}. Veuillez obtenir un extrait plus récent.")
                else:
                    r["message"] = (f"Extrait de naissance périmé. Il doit dater de moins de {mois} mois. "
                                    f"Délivré le {infos['date_delivrance']}. Veuillez en obtenir un nouveau.")

    # 3. Certificat de résidence : < 2 mois (Article 20)
    if type_doc == "CERTIFICAT_RESIDENCE":
        deliv = _parser_date(infos.get("date_delivrance"))
        if deliv:
            limite = aujourdhui - timedelta(days=60) # 2 mois
            if deliv < limite:
                r["residence_perimee"] = True
                r["message"] = (f"Certificat de résidence périmé. Il doit dater de moins de 2 mois. "
                                f"Délivré le {infos['date_delivrance']}. Veuillez en obtenir un nouveau.")

    # 4. Certificat de présence au corps (Militaires) : < 6 mois
    if type_doc == "CERTIFICAT_PRESENCE_CORPS":
        deliv = _parser_date(infos.get("date_delivrance"))
        if deliv:
            limite = aujourdhui - timedelta(days=180) # 6 mois
            if deliv < limite:
                r["residence_perimee"] = True
                r["message"] = (f"Certificat de présence au corps périmé. Il doit dater de moins de 6 mois. "
                                f"Délivré le {infos['date_delivrance']}. Veuillez en obtenir un nouveau.")

    return r


def verifier_residence_couple(infos_epoux: dict, infos_epouse: dict) -> dict:
    """
    Vérifie la règle Article 20 : l'UN des deux futurs époux doit résider dans la Commune de Cocody.
    À appeler une fois que les 2 certificats ont été analysés individuellement.
    """
    epoux_cocody = infos_epoux.get("reside_cocody", False)
    epouse_cocody = infos_epouse.get("reside_cocody", False)
    au_moins_un_cocody = epoux_cocody or epouse_cocody

    return {
        "epoux_reside_cocody": epoux_cocody,
        "epouse_reside_cocody": epouse_cocody,
        "regle_article20_respectee": au_moins_un_cocody,
        "commune_epoux": infos_epoux.get("commune_residence"),
        "commune_epouse": infos_epouse.get("commune_residence"),
        "message": None if au_moins_un_cocody else (
            "Aucun des deux futurs époux ne semble résider dans la Commune de Cocody. "
            "Selon l'Article 20, l'un des deux doit y résider. Vérification manuelle requise."
        )
    }


def determiner_action(correspondance: dict, dates: dict, est_lisible: bool = True) -> dict:
    """Détermine l'action finale basée sur tous les contrôles."""
    
    # 1. Document illisible
    if not est_lisible:
        return {
            "action": "REUPLOADER",
            "message": "Votre document est illisible. Veuillez prendre une photo plus nette, bien éclairée et bien cadrée."
        }

    # 2. Dates invalides -> REJETER immédiatement
    if dates["piece_expiree"] or dates["extrait_perime"] or dates.get("residence_perimee"):
        return {"action": "REJETER", "message": dates["message"]}

    score = correspondance.get("score_global", 0)
    date_ok = correspondance.get("date_naissance_ok")
    piece_ok = correspondance.get("numero_piece_ok")

    # 3. Cas particulier : Certificat de résidence / présence au corps
    # (Pas de numéro de pièce ni de date de naissance à comparer strictement)
    if not correspondance.get("details", {}).get("numero_piece") and not correspondance.get("details", {}).get("date_naissance"):
        if score >= 75:
            return {"action": "ACCEPTER", "message": "Document validé avec succès ✅"}
        if score >= 50:
            return {
                "action": "VERIFIER_MANUELLEMENT",
                "message": "Le nom sur le document ne correspond pas exactement aux données déclarées. Vérification manuelle requise."}
        return {
            "action": "REJETER",
            "message": "Le nom sur le document ne correspond pas aux données déclarées. Vérifiez vos informations ou contactez la mairie."
        }

    # 4. Cas général : CNI / Passeport / Extrait de naissance
    if score >= 75 and date_ok and piece_ok:
        return {"action": "ACCEPTER", "message": "Document validé avec succès ✅"}

    if score >= 50:
        return {
            "action": "VERIFIER_MANUELLEMENT",
            "message": "Des informations du document ne correspondent pas exactement aux données déclarées. Vérification manuelle requise."
        }

    return {
        "action": "REJETER",
        "message": "Les informations du document ne correspondent pas aux données que vous avez déclarées. Vérifiez vos informations ou contactez la mairie."
    }
