import re
import unicodedata
from datetime import datetime, timedelta


def normaliser_nom(texte: str) -> str:
    if not texte:
        return ""
    texte = unicodedata.normalize('NFD', texte)
    texte = ''.join(
        c for c in texte
        if unicodedata.category(c) != 'Mn'
    )
    texte = texte.upper()
    texte = re.sub(r"['\-\s]", "", texte)
    for mention in [
        'EPOUSE', 'NEE', 'VEUVE',
        'VE', 'DIVORCE', 'NE'
    ]:
        texte = texte.replace(mention, "")
    return texte.strip()


COMMUNES_ABIDJAN = [
    "COCODY", "ABOBO", "ADJAME", "ATTECOUBE", "PLATEAU",
    "KOUMASSI", "MARCORY", "PORT-BOUET", "PORT BOUET",
    "TREICHVILLE", "YOPOUGON", "ANYAMA", "BINGERVILLE",
    "SONGON"
]


def _parser_date(date_str: str):
    """Parse une date JJ/MM/AAAA en toute securite, retourne None si invalide."""
    if not date_str:
        return None
    try:
        date_normalisee = date_str.replace("-", "/").replace(".", "/")
        return datetime.strptime(date_normalisee, "%d/%m/%Y")
    except ValueError:
        return None


def parser_document(texte: str, type_doc: str) -> dict:
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

    t = texte.upper()

    if any(x in t for x in [
        "CARTE NATIONALE", "CNI", "IDENTITE", "IVOIRIEN"
    ]):
        infos["type_detecte"] = "CNI"
    elif "PASSEPORT" in t:
        infos["type_detecte"] = "PASSEPORT"
    elif any(x in t for x in [
        "NAISSANCE", "EXTRAIT", "ACTE", "ETAT CIVIL"
    ]) and "RESIDENCE" not in t:
        infos["type_detecte"] = "EXTRAIT_NAISSANCE"
    elif any(x in t for x in [
        "PRESENCE AU CORPS", "PRESENCE A CORPS", "CERTIFICAT DE PRESENCE"
    ]):
        infos["type_detecte"] = "CERTIFICAT_PRESENCE_CORPS"
    elif any(x in t for x in [
        "CERTIFICAT DE RESIDENCE", "ATTESTATION DE RESIDENCE",
        "CERTIFICAT DE DOMICILE", "RESIDENCE"
    ]):
        infos["type_detecte"] = "CERTIFICAT_RESIDENCE"

    cni = re.search(r'\bCI\d{10}\b', t)
    if cni:
        infos["numero_piece"] = cni.group()

    if not cni:
        psp = re.search(r'\b[A-Z]{1,2}\d{7,9}\b', t)
        if psp:
            infos["numero_piece"] = psp.group()

    patterns_delivrance = [
        r'D[EÉ]LIVR[EÉ]\s+LE\s*[:\s]*([\d/\-\.]{10})',
        r'FAIT\s+[AÀ]\s+\w+\s*[,\s]+LE\s*([\d/\-\.]{10})',
        r'CERTIFI[EÉ]\s+CONFORME\s+LE\s*([\d/\-\.]{10})',
        r'LE\s+PRESENT\s+EXTRAIT\s+EST\s+D[EÉ]LIVR[EÉ]\s+LE\s*([\d/\-\.]{10})',
        r'CERTIFIE\s+LE\s*[:\s]*([\d/\-\.]{10})',
        r'ABIDJAN\s*[,\s]+LE\s*([\d/\-\.]{10})'
    ]
    for pattern in patterns_delivrance:
        m = re.search(pattern, t)
        if m:
            infos["date_delivrance"] = \
                m.group(1).replace('-', '/').replace('.', '/')
            break

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

    pays_etrangers = [
        "FRANCE", "MALI", "SENEGAL", "BURKINA", "GHANA", "GUINEE",
        "NIGERIA", "NIGER", "TOGO", "BENIN", "CAMEROUN", "CONGO",
        "GABON", "LIBERIA", "MAURITANIE"
    ]
    for pays in pays_etrangers:
        if pays in t:
            infos["lieu_naissance_etranger"] = True
            break

    if infos["type_detecte"] in ("CERTIFICAT_RESIDENCE", "CERTIFICAT_PRESENCE_CORPS"):
        for commune in COMMUNES_ABIDJAN:
            if commune in t:
                infos["commune_residence"] = commune
                if commune == "COCODY":
                    infos["reside_cocody"] = True
                break

    return infos


def verifier_correspondance(infos: dict, declarees: dict) -> dict:
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

    if infos.get("nom") and declarees.get("nom"):
        nom_doc = normaliser_nom(infos["nom"])
        nom_dec = normaliser_nom(declarees["nom"])
        r["nom_ok"] = nom_doc == nom_dec
        r["details"]["nom"] = {"document": nom_doc, "declare": nom_dec}

    if infos.get("prenoms") and declarees.get("prenoms"):
        pre_doc = normaliser_nom(infos["prenoms"])
        pre_dec = normaliser_nom(declarees["prenoms"])
        r["prenoms_ok"] = pre_doc == pre_dec
        r["details"]["prenoms"] = {"document": pre_doc, "declare": pre_dec}

    if infos.get("date_naissance") and declarees.get("date_naissance"):
        d_doc = infos["date_naissance"].replace("-", "/").replace(".", "/")
        d_dec = declarees["date_naissance"].replace("-", "/").replace(".", "/")
        r["date_naissance_ok"] = d_doc == d_dec
        r["details"]["date_naissance"] = {"document": d_doc, "declare": d_dec}

    if infos.get("numero_piece") and declarees.get("numero_piece"):
        n_doc = infos["numero_piece"].upper().strip()
        n_dec = declarees["numero_piece"].upper().strip()
        r["numero_piece_ok"] = n_doc == n_dec
        r["details"]["numero_piece"] = {"document": n_doc, "declare": n_dec}

    if infos.get("type_detecte") in ("CERTIFICAT_RESIDENCE", "CERTIFICAT_PRESENCE_CORPS"):
        checks = [r["nom_ok"], r["prenoms_ok"]]
    else:
        checks = [
            r["nom_ok"], r["prenoms_ok"],
            r["date_naissance_ok"], r["numero_piece_ok"]
        ]

    r["score_global"] = sum(checks) / len(checks) * 100 if checks else 0
    return r


def verifier_dates(infos: dict, type_doc: str, date_mariage: str = None) -> dict:
    """
    date_mariage (optionnel, format JJ/MM/AAAA) :
    - Si fourni : utilise comme reference pour la validite
      de l'extrait de naissance ("< 3 mois A LA DATE DU MARIAGE").
    - Si absent (cas normal a l'upload initial, avant que
      la date de mariage soit choisie) : utilise la date du jour
      comme reference provisoire.
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

    # ── CNI / Passeport : toujours verifie contre aujourd'hui ──
    exp = _parser_date(infos.get("date_expiration"))
    if exp and exp < aujourdhui:
        r["piece_expiree"] = True
        r["message"] = (
            f"Votre piece d'identite est expiree depuis le "
            f"{infos['date_expiration']}. "
            f"Veuillez fournir une piece valide."
        )

    # ── Extrait de naissance : < 3 mois (CI) / 6 mois (etranger) ──
    # ── A LA DATE DU MARIAGE (Article 2 et 15) ──
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
                    r["message"] = (
                        f"Extrait de naissance perime a la date du "
                        f"mariage prevue ({date_mariage}). Il doit "
                        f"dater de moins de {mois} mois par rapport "
                        f"a la date du mariage. Delivre le "
                        f"{infos['date_delivrance']}. "
                        f"Veuillez obtenir un extrait plus recent "
                        f"ou choisir une date de mariage plus proche."
                    )
                else:
                    r["message"] = (
                        f"Extrait de naissance perime. Il doit dater "
                        f"de moins de {mois} mois. Delivre le "
                        f"{infos['date_delivrance']}. "
                        f"Veuillez en obtenir un nouveau aupres de "
                        f"votre mairie d'etat civil."
                    )

    # ── Certificat de residence : < 2 mois (Article 20) ──
    if type_doc == "CERTIFICAT_RESIDENCE":
        deliv = _parser_date(infos.get("date_delivrance"))
        if deliv:
            limite = aujourdhui - timedelta(days=60)
            if deliv < limite:
                r["residence_perimee"] = True
                r["message"] = (
                    f"Certificat de residence perime. Il doit dater "
                    f"de moins de 2 mois. Delivre le "
                    f"{infos['date_delivrance']}. "
                    f"Veuillez en obtenir un nouveau."
                )

    # ── Certificat de presence au corps (militaires) : < 6 mois ──
    if type_doc == "CERTIFICAT_PRESENCE_CORPS":
        deliv = _parser_date(infos.get("date_delivrance"))
        if deliv:
            limite = aujourdhui - timedelta(days=180)
            if deliv < limite:
                r["residence_perimee"] = True
                r["message"] = (
                    f"Certificat de presence au corps perime. Il doit "
                    f"dater de moins de 6 mois. Delivre le "
                    f"{infos['date_delivrance']}. "
                    f"Veuillez en obtenir un nouveau aupres de votre "
                    f"hierarchie."
                )

    return r


def verifier_residence_couple(infos_epoux: dict, infos_epouse: dict) -> dict:
    """Article 20 : l'UN des deux futurs epoux doit resider a Cocody."""
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
            "Aucun des deux futurs epoux ne semble resider dans la "
            "Commune de Cocody. Selon l'Article 20, l'un des deux "
            "doit y resider. Verification manuelle requise."
        )
    }


def determiner_action(correspondance: dict, dates: dict, est_lisible: bool = True) -> dict:
    if not est_lisible:
        return {
            "action": "REUPLOADER",
            "message": (
                "Votre document est illisible. Veuillez prendre une "
                "photo plus nette, bien eclairee et bien cadree."
            )
        }

    if dates["piece_expiree"] or dates["extrait_perime"] or dates.get("residence_perimee"):
        return {"action": "REJETER", "message": dates["message"]}

    score = correspondance.get("score_global", 0)
    date_ok = correspondance.get("date_naissance_ok")
    piece_ok = correspondance.get("numero_piece_ok")

    if not correspondance.get("details", {}).get("numero_piece") and \
       not correspondance.get("details", {}).get("date_naissance"):
        if score >= 75:
            return {"action": "ACCEPTER", "message": "Document valide avec succes"}
        if score >= 50:
            return {
                "action": "VERIFIER_MANUELLEMENT",
                "message": (
                    "Le nom sur le document ne correspond pas exactement "
                    "aux donnees declarees. Verification manuelle requise."
                )
            }
        return {
            "action": "REJETER",
            "message": (
                "Le nom sur le document ne correspond pas aux donnees "
                "declarees. Verifiez vos informations ou contactez la mairie."
            )
        }

    if score >= 75 and date_ok and piece_ok:
        return {"action": "ACCEPTER", "message": "Document valide avec succes"}

    if score >= 50:
        return {
            "action": "VERIFIER_MANUELLEMENT",
            "message": (
                "Des informations du document ne correspondent pas "
                "exactement aux donnees declarees. "
                "Verification manuelle requise."
            )
        }

    return {
        "action": "REJETER",
        "message": (
            "Les informations du document ne correspondent pas aux "
            "donnees que vous avez declarees. Verifiez vos informations "
            "ou contactez la mairie."
        )
    }
