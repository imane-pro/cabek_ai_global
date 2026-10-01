from __future__ import annotations

import re
import unicodedata


# ============================================================
# TARIF HORAIRE
# ============================================================

TARIF_MOT_DH = 70


# ============================================================
# MAPPING MODELE -> CODE BAREME T1
# ============================================================

PIECE_MODELE_VERS_T1: dict[str, str] = {

    # --------------------------------------------------------
    # Avant
    # --------------------------------------------------------

    "p_pare-chocs avant": "PARE CHOC AV",

    "p_calandre": "CALANDRE",

    "p_phare avant gauche": "OPTIQUE G",
    "p_phare avant droit": "OPTIQUE D",

    "p_aile avant gauche": "AILE AVG",
    "p_aile avant droite": "AILE AVD",

    "p_capot": "CAPOT MOTEUR",

    "p_pare-brise avant": "PARE BRISE",


    # --------------------------------------------------------
    # Roues
    # --------------------------------------------------------

    "p_roue": "JANTE",
    "p_pneu": "PNEU",


    # --------------------------------------------------------
    # Arrière
    # --------------------------------------------------------

    "p_pare-chocs arrière": "PARE CHOC AR",

    "p_feu arrière gauche": "FEU ARG",
    "p_feu arrière droit": "FEU ARD",

    "p_aile arrière gauche": "AILE ARG",
    "p_aile arrière droite": "AILE ARD",

    "p_coffre": "MALLE AR",

    "p_pare-brise arrière": "PARE BRISE",


    # --------------------------------------------------------
    # Portes
    # --------------------------------------------------------

    "p_porte avant gauche": "PORTE AVG",
    "p_porte avant droite": "PORTE AVD",

    "p_porte arrière gauche": "PORTE ARG",
    "p_porte arrière droite": "PORTE ARD",


    # --------------------------------------------------------
    # Vitres
    # --------------------------------------------------------

    "p_vitre": "VITRE PORTE AVG/AVD",


    # --------------------------------------------------------
    # Bas de caisse
    # --------------------------------------------------------

    "p_bas de caisse": "BAS CAISSE G/D",


    # --------------------------------------------------------
    # Rétroviseurs
    # --------------------------------------------------------

    "p_rétroviseur gauche": "RETROVISEUR G/D",
    "p_rétroviseur droit": "RETROVISEUR G/D",
}


# ============================================================
# HEURES T1
# ============================================================

BAREME_MOT_T1: dict[str, float] = {

    "PARE CHOC AV": 4.0,
    "CALANDRE": 0.7,

    "OPTIQUE G": 0.9,
    "OPTIQUE D": 0.9,

    "AILE AVG": 4.0,
    "AILE AVD": 4.0,

    "CAPOT MOTEUR": 4.0,
    "PARE BRISE": 4.0,

    "JANTE": 0.5,
    "PNEU": 0.5,

    "PARE CHOC AR": 3.0,

    "FEU ARG": 0.7,
    "FEU ARD": 0.7,

    "AILE ARG": 14.0,
    "AILE ARD": 14.0,

    "MALLE AR": 5.0,

    "PORTE AVG": 5.0,
    "PORTE AVD": 5.0,

    "PORTE ARG": 5.0,
    "PORTE ARD": 5.0,

    "VITRE PORTE AVG/AVD": 2.0,
    "VITRE PORTE ARG/ARD": 2.0,

    "BAS CAISSE G/D": 11.0,

    "RETROVISEUR G/D": 1.0,
}


# ============================================================
# NORMALISATION
# ============================================================

def normaliser_nom_piece(nom: str) -> str:

    if not isinstance(nom, str):
        return ""

    nom = nom.strip().lower()

    # Supprimer les accents
    nom = unicodedata.normalize("NFD", nom)

    nom = "".join(
        c
        for c in nom
        if unicodedata.category(c) != "Mn"
    )

    # Uniformiser les tirets
    nom = nom.replace("–", "-")
    nom = nom.replace("—", "-")

    # Espaces multiples
    nom = re.sub(r"\s+", " ", nom)

    return nom


# ============================================================
# MAPPING NORMALISE
# ============================================================

PIECE_MODELE_VERS_T1_NORMALISE = {
    normaliser_nom_piece(piece): code
    for piece, code in PIECE_MODELE_VERS_T1.items()
}


# ============================================================
# OBTENIR LE CODE T1
# ============================================================

def get_code_t1(nom_piece_modele: str) -> str | None:

    nom_normalise = normaliser_nom_piece(
        nom_piece_modele
    )

    return PIECE_MODELE_VERS_T1_NORMALISE.get(
        nom_normalise
    )


# ============================================================
# CALCUL MOT
# ============================================================

def calculer_cout_mot_t1(nom_piece_modele: str) -> dict:

    code_t1 = get_code_t1(nom_piece_modele)

    if code_t1 is None:

        return {
            "piece_modele": nom_piece_modele,
            "code_t1": None,
            "heures_mot": None,
            "tarif_horaire": TARIF_MOT_DH,
            "cout_mot": None,
            "status": "piece_inconnue",
        }

    heures = BAREME_MOT_T1.get(code_t1)

    if heures is None:

        return {
            "piece_modele": nom_piece_modele,
            "code_t1": code_t1,
            "heures_mot": None,
            "tarif_horaire": TARIF_MOT_DH,
            "cout_mot": None,
            "status": "bareme_manquant",
        }

    cout = heures * TARIF_MOT_DH

    return {
        "piece_modele": nom_piece_modele,
        "code_t1": code_t1,
        "heures_mot": heures,
        "tarif_horaire": TARIF_MOT_DH,
        "cout_mot": cout,
        "status": "ok",
    }


# ============================================================
# ORCHESTRATEUR — MOT + prix pièce (API AutoEstimate)
# ============================================================

def calculer_cout_remplacement(nom_piece_modele: str, prix_piece: float | None = None, type_piece: str | None = None) -> dict:
    """
    Coût complet d'un remplacement de pièce :
        total = MOT (barème T1 ci-dessus) + prix_piece (fourni par
                l'appelant — typiquement récupéré via l'API AutoEstimate,
                voir core/parts_pricing.py et core/parts_mapping.py)

    nom_piece_modele : nom brut renvoyé par le modèle IA "pièces"
                        (ex. "p_Aile arriere droite")
    prix_piece        : prix de la pièce en MAD, ou None si pas encore
                        récupéré (le total reste alors partiel/None, avec
                        un avertissement clair — jamais une valeur inventée)
    type_piece         : "original" / "adaptable" / "occasion" — reporté
                        tel quel pour traçabilité
    """
    mot = calculer_cout_mot_t1(nom_piece_modele)
    cout_mot = mot.get("cout_mot")

    resultat = {
        "piece_ai": nom_piece_modele,
        "heures_mot": mot.get("heures_mot"),
        "cout_mot": cout_mot,
        "prix_piece": prix_piece,
        "type_piece": type_piece,
        "total": None,
    }

    avertissements = []
    if mot.get("status") == "piece_inconnue":
        avertissements.append(f"Pièce '{nom_piece_modele}' non reconnue dans le barème MOT T1.")
    elif mot.get("status") == "bareme_manquant":
        avertissements.append(f"Pas d'heures MOT pour le code '{mot.get('code_t1')}' — à chiffrer manuellement.")
    if prix_piece is None:
        avertissements.append("Prix pièce non disponible (API AutoEstimate) — à chiffrer manuellement.")

    if cout_mot is not None and prix_piece is not None:
        resultat["total"] = round(cout_mot + prix_piece, 2)

    if avertissements:
        resultat["avertissement"] = " ".join(avertissements)

    return resultat