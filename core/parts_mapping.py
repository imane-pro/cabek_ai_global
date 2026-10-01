"""
Mapping des classes du modèle CABEK vers les IDs AutoEstimate.

Le modèle CABEK possède 25 classes.
L'API AutoEstimate possède 48 types de pièces.

Certaines classes CABEK regroupent plusieurs pièces AutoEstimate.
Dans ces cas, on utilise un ID représentatif selon la règle métier
de tarification du projet.
"""

from __future__ import annotations

import re
import unicodedata


# ============================================================
# MAPPING CABEK -> AUTOESTIMATE
# ============================================================

PIECE_CABEK_VERS_AUTOESTIMATE: dict[str, int] = {

    # --------------------------------------------------------
    # Pneus / roues
    # --------------------------------------------------------

    # Aucun ID correspondant dans la liste /api/v1/parts fournie.
    # "p_pneu": ???,
    # "p_roue": ???,


    # --------------------------------------------------------
    # Carrosserie avant
    # --------------------------------------------------------

    "p_pare-chocs avant": 31,

    "p_calandre": 11,

    "p_capot": 13,

    "p_aile avant gauche": 4,

    "p_aile avant droite": 3,


    # --------------------------------------------------------
    # Carrosserie arrière
    # --------------------------------------------------------

    "p_pare-chocs arrière": 30,

    "p_aile arrière gauche": 2,

    "p_aile arrière droite": 1,

    # Le modèle appelle cette pièce "Coffre".
    # AutoEstimate l'appelle "Malle Arrière".
    "p_coffre": 25,


    # --------------------------------------------------------
    # Portes
    # --------------------------------------------------------

    "p_porte avant gauche": 35,

    "p_porte avant droite": 34,

    "p_porte arrière gauche": 33,

    "p_porte arrière droite": 32,


    # --------------------------------------------------------
    # Optiques
    # --------------------------------------------------------

    # "Phare" du modèle = "Optique Avant" dans AutoEstimate.

    "p_phare avant gauche": 28,

    "p_phare avant droit": 27,


    # --------------------------------------------------------
    # Feux arrière
    # --------------------------------------------------------

    "p_feu arrière gauche": 18,

    "p_feu arrière droit": 17,


    # --------------------------------------------------------
    # Rétroviseurs
    # --------------------------------------------------------

    "p_rétroviseur gauche": 41,

    "p_rétroviseur droit": 40,


    # --------------------------------------------------------
    # Vitrage
    # --------------------------------------------------------

    # La classe "p_vitre" du modèle regroupe les 4 vitres
    # de portes.
    #
    # Les IDs AutoEstimate sont :
    #
    # 45 = arrière droit
    # 46 = arrière gauche
    # 47 = avant droit
    # 48 = avant gauche
    #
    # Selon ta règle métier, le prix est considéré identique.
    # On utilise donc l'ID 47 comme ID représentatif.

    "p_vitre": 47,


    # Le modèle distingue pare-brise avant/arrière.
    #
    # API :
    # 29 = Pare-brise
    # 24 = Lunette Arrière

    "p_pare-brise avant": 29,

    "p_pare-brise arrière": 24,


    # --------------------------------------------------------
    # Bas de caisse
    # --------------------------------------------------------

    # API :
    # 9  = Bas De Caisse Droit
    # 10 = Bas De Caisse Gauche
    #
    # Le modèle possède une seule classe "p_bas de caisse".
    # Le prix étant considéré identique G/D, on utilise l'ID 10.

    "p_bas de caisse": 10,
}


# ============================================================
# INFORMATIONS DES CLASSES SANS ID
# ============================================================

PIECES_SANS_ID_AUTOESTIMATE = {

    "p_pneu": {
        "raison": (
            "Aucun type 'Pneu' n'est présent dans la liste "
            "des 48 pièces AutoEstimate fournie."
        )
    },

    "p_roue": {
        "raison": (
            "Aucun type 'Roue' n'est présent dans la liste "
            "des 48 pièces AutoEstimate fournie."
        )
    },
}


# ============================================================
# NORMALISATION
# ============================================================

def normaliser_nom_piece(nom: str) -> str:
    """
    Normalise le nom provenant du modèle.

    Exemple :

        p_Aile arrière gauche
        P_AILE ARRIÈRE GAUCHE
        p_aile arrière gauche

    deviennent :

        p_aile arriere gauche
    """

    if not isinstance(nom, str):
        return ""

    nom = nom.strip().lower()

    # Suppression des accents
    nom = unicodedata.normalize("NFD", nom)

    nom = "".join(
        c
        for c in nom
        if unicodedata.category(c) != "Mn"
    )

    # Normalisation des tirets
    nom = nom.replace("–", "-")
    nom = nom.replace("—", "-")

    # Espaces multiples
    nom = re.sub(r"\s+", " ", nom)

    return nom


# ============================================================
# MAPPING NORMALISÉ
# ============================================================

PIECE_CABEK_VERS_AUTOESTIMATE_NORMALISE = {
    normaliser_nom_piece(nom): part_id
    for nom, part_id in PIECE_CABEK_VERS_AUTOESTIMATE.items()
}


# ============================================================
# GET PART ID
# ============================================================

def get_part_id(nom_piece: str) -> int | None:
    """
    Retourne l'ID AutoEstimate correspondant à une classe CABEK.

    Exemple :

        get_part_id("p_Aile arrière gauche")
        -> 2
    """

    nom_normalise = normaliser_nom_piece(nom_piece)

    return PIECE_CABEK_VERS_AUTOESTIMATE_NORMALISE.get(
        nom_normalise
    )


# ============================================================
# TEST / DEBUG
# ============================================================

if __name__ == "__main__":

    tests = [
        "p_Aile arrière gauche",
        "p_Aile arrière droite",
        "p_Aile avant gauche",
        "p_Aile avant droite",
        "p_Pare-chocs avant",
        "p_Pare-chocs arrière",
        "p_Phare avant droit",
        "p_Phare avant gauche",
        "p_Coffre",
        "p_Pare-brise avant",
        "p_Pare-brise arrière",
        "p_vitre",
        "p_bas de caisse",
        "p_Pneu",
        "p_Roue",
    ]

    print("\n=== TEST MAPPING CABEK -> AUTOESTIMATE ===\n")

    for piece in tests:

        part_id = get_part_id(piece)

        print(
            f"{piece:<30} -> "
            f"{part_id if part_id is not None else 'AUCUN ID'}"
        )