"""
Moteur d'expertise CABEK.

Fonctionnalités :
- Détection des dommages et pièces avec YOLO
- Association dommage <-> pièce
- Calcul de gravité
- Détection des zones critiques
- Déduplication multi-vues
- Règles métier de remplacement
- Chiffrage réparation / remplacement
- Prix pièces via AutoEstimate
- Validation humaine par le chiffreur
- Exclusion des détections rejetées du chiffrage
- Conservation des détections rejetées pour feedback / retraining
"""

from __future__ import annotations

import cv2
import hashlib
import json

import numpy as np

from bareme_c2 import (
    calculer_cout_dommage,
    TARIF_REPARATION_DH,
    TARIF_MOP_DH,
)

from bareme_t1 import calculer_cout_remplacement


# ============================================================
# 1. CONFIGURATION
# ============================================================

POIDS_CATEGORIE = {
    "d_brise": 0.9,
    "d_piece_manquante": 0.9,
    "d_casse": 0.8,
    "d_lampe_casse": 0.6,
    "d_bosse": 0.5,
    "d_fissure": 0.5,
    "d_crevaison": 0.7,
    "d_rayure": 0.3,
}


CLASSES_SANS_SURFACE = [
    "d_crevaison",
]


SOLUTIONS = {
    "d_rayure": "Polissage / peinture partielle",
    "d_bosse": "Débosselage / redressage",
    "d_fissure": "Réparation / mastic",
    "d_brise": "Remplacement vitrage",
    "d_casse": "Échange pièce",
    "d_lampe_casse": "Réparation ou remplacement optique",
    "d_piece_manquante": "Échange pièce",
    "d_crevaison": "Réparation / remplacement pneu",
}


# ============================================================
# 2. VALIDATION EXPERT
# ============================================================
#
# Chaque détection possède un état :
#
#   a_valider
#       ↓
#   acceptee
#
# ou
#
#   a_valider
#       ↓
#   rejetee
#
# Une détection rejetée reste dans les données mais est exclue
# de tous les calculs financiers.
# ============================================================

VALIDATIONS_AUTORISEES = {
    "a_valider",
    "acceptee",
    "rejetee",
}


def normaliser_validation(validation: str | None) -> str:
    """
    Normalise le statut de validation expert.

    Toute valeur inconnue est considérée comme 'a_valider'
    afin d'éviter qu'une valeur incorrecte puisse être
    automatiquement incluse dans un calcul.
    """

    valeur = str(validation or "a_valider").strip().lower()

    if valeur not in VALIDATIONS_AUTORISEES:
        return "a_valider"

    return valeur


def detection_valide_pour_chiffrage(item: dict) -> bool:
    """
    Retourne True uniquement si la détection n'est pas rejetée.

    Important :
    - 'acceptee' -> chiffrage autorisé
    - 'a_valider' -> chiffrage temporairement autorisé
      afin de conserver le fonctionnement actuel de l'application
    - 'rejetee' -> chiffrage INTERDIT

    Le dossier pourra ensuite être bloqué à la validation finale
    tant qu'il reste des éléments 'a_valider'.
    """

    validation = normaliser_validation(
        item.get("validation_expert")
    )

    return validation != "rejetee"


def detection_acceptee(item: dict) -> bool:
    """Retourne True si l'expert a explicitement accepté la détection."""

    return (
        normaliser_validation(
            item.get("validation_expert")
        )
        == "acceptee"
    )


def detection_rejetee(item: dict) -> bool:
    """Retourne True si l'expert a rejeté la détection."""

    return (
        normaliser_validation(
            item.get("validation_expert")
        )
        == "rejetee"
    )


def detection_a_valider(item: dict) -> bool:
    """Retourne True si la détection attend encore une validation."""

    return (
        normaliser_validation(
            item.get("validation_expert")
        )
        == "a_valider"
    )


def initialiser_validation(item: dict) -> dict:
    """
    Initialise les champs de validation d'une détection.

    Cette fonction ne modifie pas une validation déjà existante.
    """

    item.setdefault("validation_expert", "a_valider")

    item.setdefault("feedback_raison", "")
    item.setdefault("feedback_observation", "")

    item.setdefault("piece_corrigee", "")
    item.setdefault("dommage_corrige", "")

    item["validation_expert"] = normaliser_validation(
        item.get("validation_expert")
    )

    return item


def appliquer_validation_rejetee(item: dict) -> dict:
    """
    Applique immédiatement les conséquences d'un rejet expert.

    La détection n'est PAS supprimée.

    Elle reste disponible pour :
    - analyse des erreurs IA
    - statistiques
    - amélioration des annotations
    - futur retraining YOLO
    """

    item["validation_expert"] = "rejetee"

    # Le rejet doit neutraliser le chiffrage.
    item["remplacement_requis"] = False
    item["chiffrage_bloque"] = True

    item["cout"] = None
    item["prix_piece"] = None
    item["cout_mot"] = None

    item["cout_detail"] = {
        "type": "detection_rejetee",
        "remplacement_requis": False,
        "total": None,
        "avertissement": (
            "Détection rejetée par le chiffreur. "
            "Cette détection est conservée pour le feedback "
            "et n'est pas incluse dans le chiffrage."
        ),
    }

    return item


def appliquer_validation_acceptee(item: dict) -> dict:
    """
    Marque une détection comme acceptée.

    Le calcul du coût sera effectué par les fonctions métier
    normales.
    """

    item["validation_expert"] = "acceptee"

    # Si le rejet avait précédemment neutralisé l'élément,
    # on remet les indicateurs à zéro.
    item["chiffrage_bloque"] = False

    return item


def appliquer_feedback_aux_instances(
    instances: list,
    feedbacks: list | None,
) -> list:
    """
    Recharge les validations sauvegardées dans feedback.json
    et les applique aux instances actuellement chargées.

    Le lien se fait principalement avec detection_id.

    Les feedbacks plus anciens dont la détection n'existe plus
    dans l'analyse actuelle sont simplement ignorés.
    """

    if not feedbacks:
        for item in instances:
            initialiser_validation(item)
        return instances

    feedback_by_detection_id = {}

    for feedback in feedbacks:

        detection_id = feedback.get("detection_id")

        if not detection_id:
            continue

        feedback_by_detection_id[str(detection_id)] = feedback

    for item in instances:

        initialiser_validation(item)

        detection_id = item.get("detection_id")

        if not detection_id:
            continue

        feedback = feedback_by_detection_id.get(
            str(detection_id)
        )

        if not feedback:
            continue

        validation = normaliser_validation(
            feedback.get("validation")
        )

        item["validation_expert"] = validation

        item["feedback_raison"] = feedback.get(
            "raison",
            "",
        )

        item["feedback_observation"] = feedback.get(
            "observation",
            "",
        )

        item["piece_corrigee"] = feedback.get(
            "piece_corrigee",
            "",
        )

        item["dommage_corrige"] = feedback.get(
            "dommage_corrige",
            "",
        )

        item["action_experte"] = normaliser_action(
            feedback.get("action_experte")
        )

        if validation == "rejetee":
            appliquer_validation_rejetee(item)

        elif validation == "acceptee":
            appliquer_validation_acceptee(item)

    return instances


# ============================================================
# 3. DÉCISION EXPERTE — ACTION DE CHIFFRAGE
# ============================================================

ACTIONS_CHIFFRAGE = {
    "reparation": "Réparation",
    "remplacement": "Remplacement",
}


def normaliser_action(action: str | None) -> str:
    """Normalise la décision finale de chiffrage."""
    valeur = str(action or "").strip().lower()
    if valeur in ACTIONS_CHIFFRAGE:
        return valeur
    return ""


def action_effective(item: dict) -> str:
    """Retourne l'action réellement appliquée au chiffrage."""
    action_experte = normaliser_action(
        item.get("action_experte")
    )

    if action_experte:
        return action_experte

    return (
        "remplacement"
        if item.get("remplacement_requis")
        else "reparation"
    )


def appliquer_decision_experte(
    instances: list,
) -> list:
    """
    Applique la correction d'action décidée par l'expert.

    L'IA reste conservée dans ``action_ia``.
    ``action_experte`` devient la décision finale lorsqu'elle existe.

    Une correction vers ``reparation`` recalcule le coût avec le barème
    C2 via ``calculer_cout_dommage`` et retire la fourniture/MOT de
    remplacement.
    """

    # Les corrections d'action sont appliquées après les règles IA.
    for item in instances:

        if detection_rejetee(item):
            continue

        action = normaliser_action(
            item.get("action_experte")
        )

        if not action:
            # Conserver la proposition IA explicite pour l'interface.
            item["action_finale"] = (
                "remplacement"
                if item.get("remplacement_requis")
                else "reparation"
            )
            continue

        item["action_finale"] = action

        piece = item.get("piece_ai_brut")

        if action == "reparation":

            # Une correction expert vers réparation annule le remplacement
            # automatique pour cette détection.
            item["remplacement_requis"] = False
            item["chiffrage_bloque"] = False
            item["prix_piece"] = None
            item["type_piece"] = None
            item["cout_mot"] = None
            item["heures_mot"] = None

            if piece is not None:
                detail = calculer_cout_dommage(
                    piece,
                    item.get("type_brut", ""),
                    item.get("niveau", "mid"),
                )
            else:
                detail = {
                    "total": None,
                    "avertissement": (
                        "Pièce non identifiée — réparation impossible "
                        "à chiffrer automatiquement."
                    ),
                }

            item["cout"] = detail.get("total")
            item["cout_detail"] = {
                **detail,
                "type": "reparation_expert",
                "action_ia": item.get(
                    "action_ia",
                    "remplacement",
                ),
                "action_experte": "reparation",
            }

            item["solution"] = (
                "Réparation — décision expert"
            )

        elif action == "remplacement":

            # L'expert confirme le remplacement : on conserve le calcul T1
            # produit par appliquer_priorite_remplacement().
            item["remplacement_requis"] = True
            item["chiffrage_bloque"] = False

            detail_remplacement = calculer_cout_remplacement(
                piece
            ) if piece is not None else {
                "total": None,
                "cout_mot": None,
                "heures_mot": None,
                "prix_piece": None,
                "type_piece": None,
            }

            item["cout"] = detail_remplacement.get("total")
            item["cout_mot"] = detail_remplacement.get("cout_mot")
            item["heures_mot"] = detail_remplacement.get("heures_mot")

            detail = item.setdefault("cout_detail", {})
            detail.update({
                "type": "remplacement_expert",
                "remplacement_requis": True,
                "action_ia": item.get(
                    "action_ia",
                    "reparation",
                ),
                "action_experte": "remplacement",
            })

            item["solution"] = (
                "Remplacement complet de la pièce — décision expert"
            )

    return instances


# ============================================================
# 4. RÈGLES MÉTIER — PRIORITÉ AU REMPLACEMENT
# ============================================================

DOMMAGES_REMPLACEMENT_DIRECT = {
    "d_piece_manquante",
    "d_casse",
    "d_crevaison",
}


DOMMAGES_REMPLACEMENT_SI_GRAVE = {
    "d_fissure",
    "d_bosse",
    "d_brise",
    "d_lampe_casse",
}


# ============================================================
# 4. GRAVITÉ
# ============================================================

SUFFIXE_GRAVITE_CLASSE = {
    "slight": "low",
    "leger": "low",
    "light": "low",

    "medium": "mid",
    "moderate": "mid",
    "modere": "mid",
    "mid": "mid",

    "severe": "high",
    "grave": "high",
    "high": "high",
}


GRAVITE_ORDRE = {
    "low": 0,
    "mid": 1,
    "high": 2,
}


def normaliser_classe_dommage(
    nom_classe: str,
):
    """
    Normalise une classe IA et récupère sa gravité explicite éventuelle.
    """

    nom = str(nom_classe).strip().lower()

    if not nom.startswith("d_"):
        return nom, None

    base, suffixe = nom.rsplit("_", 1)

    if suffixe in SUFFIXE_GRAVITE_CLASSE:
        return (
            base,
            SUFFIXE_GRAVITE_CLASSE[suffixe],
        )

    return nom, None


def gravite_max(
    niveau_a: str,
    niveau_b: str,
) -> str:
    """Retourne le niveau de gravité le plus élevé."""

    if GRAVITE_ORDRE.get(
        niveau_b,
        0,
    ) > GRAVITE_ORDRE.get(
        niveau_a,
        0,
    ):
        return niveau_b

    return niveau_a


# ============================================================
# 5. DÉTAIL FOURNITURE
# ============================================================

def calculer_detail_fourniture(
    instances,
):
    """
    Calcule le détail des pièces à fournir.

    Les détections rejetées par l'expert sont ignorées.

    Retourne :
        - lignes
        - total_fourniture
        - n_avec_prix
        - n_sans_prix
        - complet
    """

    lignes = []

    total_fourniture = 0.0

    n_avec_prix = 0
    n_sans_prix = 0

    for item in instances:

        # --------------------------------------------------
        # DÉTECTION REJETÉE
        # --------------------------------------------------

        if not detection_valide_pour_chiffrage(item):
            continue

        # --------------------------------------------------
        # Seules les pièces nécessitant un remplacement
        # sont prises en compte.
        # --------------------------------------------------

        if not item.get(
            "remplacement_requis"
        ):
            continue

        prix_piece = item.get(
            "prix_piece"
        )

        type_piece = item.get(
            "type_piece"
        )

        if prix_piece is not None:

            try:

                prix_piece = float(
                    prix_piece
                )

                total_fourniture += prix_piece
                n_avec_prix += 1

            except (
                TypeError,
                ValueError,
            ):

                prix_piece = None
                n_sans_prix += 1

        else:

            n_sans_prix += 1

        lignes.append(
            {
                "piece": item.get(
                    "piece",
                    "—",
                ),
                "type_piece": type_piece,
                "prix_piece": prix_piece,
            }
        )

    return {
        "lignes": lignes,
        "total_fourniture": total_fourniture,
        "n_avec_prix": n_avec_prix,
        "n_sans_prix": n_sans_prix,
        "complet": n_sans_prix == 0,
    }


# ============================================================
# 6. REMPLACEMENT
# ============================================================

def necessite_remplacement(
    item: dict,
) -> bool:
    """
    Détermine si le dommage impose le remplacement complet
    de la pièce.

    Une détection rejetée ne peut jamais imposer un remplacement.
    """

    # ------------------------------------------------------
    # SÉCURITÉ : rejet expert
    # ------------------------------------------------------

    if not detection_valide_pour_chiffrage(item):
        return False

    type_dommage = item.get(
        "type_brut",
        "",
    )

    # ------------------------------------------------------
    # Zone critique
    # ------------------------------------------------------

    if (
        type_dommage == "d_bosse"
        and item.get(
            "zone_critique_detectee"
        ) is True
    ):
        return True

    niveau = item.get(
        "niveau",
        "low",
    )

    # ------------------------------------------------------
    # Remplacement direct
    # ------------------------------------------------------

    if type_dommage in DOMMAGES_REMPLACEMENT_DIRECT:
        return True

    # ------------------------------------------------------
    # Remplacement si grave
    # ------------------------------------------------------

    return (
        type_dommage in DOMMAGES_REMPLACEMENT_SI_GRAVE
        and niveau == "high"
    )


def appliquer_priorite_remplacement(
    instances: list,
) -> list:
    """
    Applique les règles métier au niveau de chaque pièce.

    Une détection rejetée par l'expert est complètement exclue
    du calcul.

    Pour une pièce nécessitant un remplacement :
        - le dommage déclencheur est chiffré ;
        - les autres dommages sont considérés comme inclus
          dans le remplacement.

    Les détections rejetées restent dans la liste.
    """

    pieces_a_remplacer = {}

    # ======================================================
    # 1. Identifier les pièces à remplacer
    # ======================================================

    for item in instances:

        # Une détection rejetée ne peut pas condamner une pièce.
        if not detection_valide_pour_chiffrage(item):
            continue

        piece = item.get(
            "piece_ai_brut"
        )

        if (
            piece is not None
            and necessite_remplacement(item)
        ):

            pieces_a_remplacer.setdefault(
                piece,
                [],
            ).append(item)

    # ======================================================
    # 2. Appliquer les règles
    # ======================================================

    for item in instances:

        # --------------------------------------------------
        # REJET EXPERT
        # --------------------------------------------------

        if detection_rejetee(item):

            appliquer_validation_rejetee(
                item
            )

            continue

        piece = item.get(
            "piece_ai_brut"
        )

        # --------------------------------------------------
        # Aucune pièce à remplacer
        # --------------------------------------------------

        if (
            piece is None
            or piece not in pieces_a_remplacer
        ):

            item["remplacement_requis"] = False
            item["chiffrage_bloque"] = False

            continue

        # --------------------------------------------------
        # Dommage déclencheur
        # --------------------------------------------------

        if necessite_remplacement(item):

            item["remplacement_requis"] = True
            item["chiffrage_bloque"] = False

            detail_remplacement = (
                calculer_cout_remplacement(
                    piece
                )
            )

            item["cout"] = (
                detail_remplacement.get(
                    "total"
                )
            )

            item["cout_mot"] = (
                detail_remplacement.get(
                    "cout_mot"
                )
            )

            item["heures_mot"] = (
                detail_remplacement.get(
                    "heures_mot"
                )
            )

            avertissement_base = (
                detail_remplacement.get(
                    "avertissement",
                    "",
                )
            )

            if (
                item.get("type_brut")
                == "d_bosse"
                and item.get(
                    "zone_critique_detectee"
                ) is True
            ):

                avertissement = (
                    "Dommage situé sur une zone critique "
                    "(arête / bord / zone structurelle) "
                    "détectée par le modèle IA — remplacement "
                    "complet de la pièce imposé, indépendamment "
                    "de la surface touchée ou de la gravité "
                    "apparente. "
                    + avertissement_base
                )

            else:

                avertissement = (
                    "Ce dommage nécessite le remplacement "
                    "complet de la pièce. "
                    + avertissement_base
                )

            item["cout_detail"] = {
                "type": "remplacement",
                "remplacement_requis": True,
                "cout_mot": detail_remplacement.get(
                    "cout_mot"
                ),
                "heures_mot": detail_remplacement.get(
                    "heures_mot"
                ),
                "prix_piece": detail_remplacement.get(
                    "prix_piece"
                ),
                "type_piece": detail_remplacement.get(
                    "type_piece"
                ),
                "total": detail_remplacement.get(
                    "total"
                ),
                "declencheur_zone_critique": item.get(
                    "zone_critique_detectee",
                    False,
                ),
                "avertissement": avertissement.strip(),
            }

            item["solution"] = (
                "Remplacement complet de la pièce"
            )

        # --------------------------------------------------
        # Autre dommage de la même pièce
        # --------------------------------------------------

        else:

            item["remplacement_requis"] = False
            item["chiffrage_bloque"] = True
            item["cout"] = None

            item["cout_detail"] = {
                "type": "inclus_dans_remplacement",
                "remplacement_requis": True,
                "total": None,
                "avertissement": (
                    "Dommage non chiffré séparément : "
                    "la pièce présente un dommage nécessitant "
                    "son remplacement complet. Ce dommage est "
                    "considéré comme inclus dans le remplacement "
                    "de la pièce."
                ),
            }

            item["solution"] = (
                "Non chiffré séparément — "
                "remplacement de la pièce requis"
            )

    # Conserver la proposition IA avant toute correction humaine.
    for item in instances:
        if detection_rejetee(item):
            continue
        item["action_ia"] = (
            "remplacement"
            if item.get("remplacement_requis")
            else "reparation"
        )

    # Correction éventuelle de l'expert : recalcul C2/T1.
    appliquer_decision_experte(instances)

    return instances


# ============================================================
# 7. IDENTIFIANT D'UNE DÉTECTION
# ============================================================

def item_key(
    item: dict,
) -> str:
    """
    Identifiant utilisé par les widgets Streamlit.

    Il reste compatible avec l'ancien fonctionnement.
    """

    sources = ",".join(
        item.get(
            "images_sources",
            [],
        )
    )

    return (
        f"{item.get('piece_ai_brut', '?')}"
        f"|{item.get('type_brut', '?')}"
        f"|{sources}"
    )


def generer_detection_id(
    item: dict,
) -> str:
    """
    Génère un identifiant déterministe pour une détection.

    L'objectif est que le même dommage puisse être retrouvé
    après un rerun de Streamlit et après rechargement du dossier.

    On utilise :
        pièce
        type dommage
        position
        images sources

    La confiance n'est volontairement PAS utilisée car elle
    peut légèrement changer entre deux exécutions.
    """

    sources = sorted(
        set(
            str(x)
            for x in item.get(
                "images_sources",
                [],
            )
        )
    )

    contenu = {
        "piece": item.get(
            "piece_ai_brut"
        ),
        "type": item.get(
            "type_brut"
        ),
        "position": item.get(
            "position_bucket",
            "inconnu",
        ),
        "sources": sources,
    }

    texte = json.dumps(
        contenu,
        ensure_ascii=False,
        sort_keys=True,
    )

    return (
        "DET-"
        + hashlib.sha1(
            texte.encode("utf-8")
        ).hexdigest()[:16].upper()
    )


# ============================================================
# 8. PRIX DES PIÈCES
# ============================================================

def enrichir_prix_pieces(
    instances: list,
    marque_id: int | None,
    model_id: int | None,
    year: int | None,
    types_choisis: dict,
) -> list:
    """
    Complète le coût des dommages nécessitant un remplacement
    avec le prix pièce récupéré via AutoEstimate.

    Une détection rejetée est toujours ignorée.
    """

    if not marque_id or not model_id:
        return instances

    from core.parts_pricing import (
        get_estimation,
        AutoEstimateError,
    )

    from core.parts_mapping import (
        get_part_id,
    )

    for item in instances:

        # --------------------------------------------------
        # REJET EXPERT
        # --------------------------------------------------

        if not detection_valide_pour_chiffrage(item):
            continue

        # --------------------------------------------------
        # Seulement remplacement
        # --------------------------------------------------

        if not item.get(
            "remplacement_requis"
        ):
            continue

        key = item_key(item)

        type_piece = types_choisis.get(
            key,
            "occasion",
        )

        piece_ai = item.get(
            "piece_ai_brut",
            "",
        )

        part_id = get_part_id(
            piece_ai
        )

        detail = item.setdefault(
            "cout_detail",
            {},
        )

        # --------------------------------------------------
        # Pièce inconnue
        # --------------------------------------------------

        if part_id is None:

            detail[
                "avertissement_api"
            ] = (
                f"Pièce '{piece_ai}' non cartographiée "
                "vers AutoEstimate "
                "(voir core/parts_mapping.py)."
            )

            continue

        # --------------------------------------------------
        # API AutoEstimate
        # --------------------------------------------------

        try:

            est = get_estimation(
                marque_id,
                model_id,
                part_id,
                type_piece,
                year,
            )

        except AutoEstimateError as e:

            detail[
                "avertissement_api"
            ] = (
                f"AutoEstimate indisponible : {e}"
            )

            continue

        if est is None:

            detail[
                "avertissement_api"
            ] = (
                "Aucune observation AutoEstimate "
                f"pour ce type ({type_piece})."
            )

            continue

        # --------------------------------------------------
        # Prix médian
        # --------------------------------------------------

        prix_piece = est.get(
            "median"
        )

        item["prix_piece"] = prix_piece

        item["type_piece"] = type_piece

        item["estimation_detail"] = est

        cout_mot = item.get(
            "cout_mot"
        )

        if (
            cout_mot is not None
            and prix_piece is not None
        ):

            item["cout"] = round(
                cout_mot + prix_piece,
                2,
            )

            detail["prix_piece"] = (
                prix_piece
            )

            detail["type_piece"] = (
                type_piece
            )

            detail["total"] = (
                item["cout"]
            )

            detail.pop(
                "avertissement_api",
                None,
            )

    return instances


# ============================================================
# 9. CATÉGORIES MARQUES
# ============================================================

CATEGORIES_MARQUE = {
    "Éco": [
        "Dacia",
        "Fiat",
        "Seat",
        "Skoda",
        "Lada",
    ],

    "Standard": [
        "Renault",
        "Peugeot",
        "Citroën",
        "Ford",
        "Toyota",
        "Hyundai",
        "Kia",
        "Volkswagen",
        "Nissan",
        "Opel",
        "Chevrolet",
        "Suzuki",
    ],

    "Premium": [
        "Mercedes",
        "BMW",
        "Audi",
        "Lexus",
        "Volvo",
        "Land Rover",
        "Porsche",
    ],
}


def get_categorie_marque(
    marque: str,
) -> str:

    for cat, marques in CATEGORIES_MARQUE.items():

        if marque in marques:
            return cat

    return "Standard"


# ============================================================
# 10. CALCUL OVERLAP
# ============================================================

def calculer_overlap(
    mask_d: np.ndarray,
    mask_p: np.ndarray,
) -> float:

    mask_d_bool = mask_d.astype(bool)
    mask_p_bool = mask_p.astype(bool)

    intersection = np.logical_and(
        mask_d_bool,
        mask_p_bool,
    ).sum()

    surface_dommage = (
        mask_d_bool.sum()
    )

    if surface_dommage == 0:
        return 0.0

    return float(
        intersection
        / surface_dommage
    )


# ============================================================
# 11. POSITION DANS LA PIÈCE
# ============================================================

def position_bucket(
    mask_d: np.ndarray,
    mask_p: np.ndarray,
) -> str:
    """
    Situe approximativement le dommage dans la pièce.

    Retour :
        HH / HD / BH / BD
        ou inconnu
    """

    ys_p, xs_p = np.where(
        mask_p
    )

    if len(xs_p) == 0:
        return "inconnu"

    x_min = xs_p.min()
    x_max = xs_p.max()

    y_min = ys_p.min()
    y_max = ys_p.max()

    ys_d, xs_d = np.where(
        mask_d
    )

    if len(xs_d) == 0:
        return "inconnu"

    cx = xs_d.mean()
    cy = ys_d.mean()

    fx = (
        cx - x_min
    ) / max(
        x_max - x_min,
        1,
    )

    fy = (
        cy - y_min
    ) / max(
        y_max - y_min,
        1,
    )

    horiz = (
        "G"
        if fx < 0.5
        else "D"
    )

    vert = (
        "H"
        if fy < 0.5
        else "B"
    )

    return f"{vert}{horiz}"


# ============================================================
# 12. SCORE DE GRAVITÉ
# ============================================================

def calculer_score_gravite(
    nom_dommage: str,
    ratio_surface: float,
    confiance: float,
    alpha: float = 0.2,
    beta: float = 0.2,
    gamma: float = 0.6,
) -> float:

    poids = POIDS_CATEGORIE.get(
        nom_dommage,
        0.5,
    )

    if nom_dommage in CLASSES_SANS_SURFACE:

        beta_a = beta / (
            beta + gamma
        )

        gamma_a = gamma / (
            beta + gamma
        )

        return (
            beta_a * confiance
            + gamma_a * poids
        )

    return (
        alpha * ratio_surface
        + beta * confiance
        + gamma * poids
    )


def score_vers_gravite(
    score: float,
) -> str:

    if score < 0.35:
        return "low"

    elif score < 0.6:
        return "mid"

    return "high"


LABEL_GRAVITE = {
    "low": "Léger",
    "mid": "Modéré",
    "high": "Grave",
}


# ============================================================
# 13. ZONE CRITIQUE
# ============================================================

def calculer_overlap_zone_critique(
    mask_d_np: np.ndarray,
    res_z,
) -> float:
    """
    Calcule le pourcentage du masque dommage qui tombe
    dans une zone critique.
    """

    if (
        res_z is None
        or res_z.masks is None
        or len(res_z.boxes) == 0
    ):
        return 0.0

    meilleur = 0.0

    for mask_z in res_z.masks.data:

        mask_z_np = (
            mask_z
            .cpu()
            .numpy()
            .astype(bool)
        )

        if (
            mask_d_np.shape
            != mask_z_np.shape
        ):

            mask_d_resized = cv2.resize(
                mask_d_np.astype(
                    np.uint8
                ),
                (
                    mask_z_np.shape[1],
                    mask_z_np.shape[0],
                ),
            ).astype(bool)

        else:

            mask_d_resized = mask_d_np

        overlap = calculer_overlap(
            mask_d_resized,
            mask_z_np,
        )

        if overlap > meilleur:
            meilleur = overlap

    return meilleur


# ============================================================
# 14. ANALYSE YOLO
# ============================================================

def analyser(
    modele_pieces,
    modele_dommages,
    image_np: np.ndarray,
    conf_pieces: float,
    conf_dommages: float,
    iou_min: float,
    marque: str,
    nom_image: str = "",
    modele_zone_critique=None,
    conf_zone_critique: float = 0.25,
    seuil_zone_critique: float = 0.05,
):
    """
    Exécute l'analyse YOLO.

    modèle pièces
        ↓
    modèle dommages
        ↓
    association dommage / pièce
        ↓
    gravité
        ↓
    zone critique
        ↓
    coût initial

    La validation expert est initialisée à 'a_valider'.
    """

    # ======================================================
    # YOLO PIÈCES
    # ======================================================

    res_p = modele_pieces.predict(
        image_np,
        conf=conf_pieces,
        agnostic_nms=True,
        verbose=False,
    )[0]

    # ======================================================
    # YOLO DOMMAGES
    # ======================================================

    res_d = modele_dommages.predict(
        image_np,
        conf=conf_dommages,
        agnostic_nms=True,
        verbose=False,
    )[0]

    # ======================================================
    # YOLO ZONE CRITIQUE
    # ======================================================

    res_z = None

    if modele_zone_critique is not None:

        res_z = modele_zone_critique.predict(
            image_np,
            conf=conf_zone_critique,
            agnostic_nms=True,
            verbose=False,
        )[0]

    instances = []

    # ======================================================
    # TRAITEMENT DES DOMMAGES
    # ======================================================

    if (
        res_d.masks is not None
        and len(res_d.boxes) > 0
    ):

        for i, mask_d in enumerate(
            res_d.masks.data
        ):

            # ------------------------------------------------
            # Classe dommage
            # ------------------------------------------------

            nom_d_ia = (
                modele_dommages.names[
                    int(
                        res_d.boxes.cls[i]
                    )
                ]
            )

            nom_d, gravite_classe = (
                normaliser_classe_dommage(
                    nom_d_ia
                )
            )

            conf_d = float(
                res_d.boxes.conf[i]
            )

            mask_d_np = (
                mask_d
                .cpu()
                .numpy()
                .astype(bool)
            )

            surface_d = (
                mask_d_np.sum()
            )

            # ------------------------------------------------
            # Recherche de la meilleure pièce
            # ------------------------------------------------

            meilleure_piece = None
            meilleur_overlap = 0.0

            if (
                res_p.masks is not None
                and len(res_p.boxes) > 0
            ):

                for j, mask_p in enumerate(
                    res_p.masks.data
                ):

                    nom_p = (
                        modele_pieces.names[
                            int(
                                res_p.boxes.cls[j]
                            )
                        ]
                    )

                    conf_p = float(
                        res_p.boxes.conf[j]
                    )

                    mask_p_np = (
                        mask_p
                        .cpu()
                        .numpy()
                        .astype(bool)
                    )

                    if (
                        mask_d_np.shape
                        != mask_p_np.shape
                    ):

                        mask_d_resized = (
                            cv2.resize(
                                mask_d_np.astype(
                                    np.uint8
                                ),
                                (
                                    mask_p_np.shape[1],
                                    mask_p_np.shape[0],
                                ),
                            ).astype(bool)
                        )

                    else:

                        mask_d_resized = (
                            mask_d_np
                        )

                    overlap = calculer_overlap(
                        mask_d_resized,
                        mask_p_np,
                    )

                    if overlap > meilleur_overlap:

                        meilleur_overlap = (
                            overlap
                        )

                        meilleure_piece = {
                            "nom": nom_p,
                            "conf": conf_p,
                            "mask": mask_p_np,
                            "mask_d_aligne": (
                                mask_d_resized
                            ),
                        }

            # ------------------------------------------------
            # Identification pièce
            # ------------------------------------------------

            piece_ai_brut = None

            bucket = "inconnu"

            if (
                meilleure_piece
                and meilleur_overlap >= iou_min
            ):

                surface_p = (
                    meilleure_piece[
                        "mask"
                    ].sum()
                )

                if surface_p >= surface_d:

                    ratio_surface = (
                        surface_d
                        / (
                            surface_p
                            + 1e-6
                        )
                    )

                    piece_ai_brut = (
                        meilleure_piece[
                            "nom"
                        ]
                    )

                    piece_nom = (
                        meilleure_piece[
                            "nom"
                        ]
                        .replace(
                            "p_",
                            "",
                        )
                        .replace(
                            "_",
                            " ",
                        )
                    )

                    bucket = position_bucket(
                        meilleure_piece[
                            "mask_d_aligne"
                        ],
                        meilleure_piece[
                            "mask"
                        ],
                    )

                else:

                    h, w = (
                        image_np.shape[:2]
                    )

                    ratio_surface = (
                        surface_d
                        / (
                            h * w
                            + 1e-6
                        )
                    )

                    piece_nom = (
                        "zone non identifiée"
                    )

            else:

                h, w = (
                    image_np.shape[:2]
                )

                ratio_surface = (
                    surface_d
                    / (
                        h * w
                        + 1e-6
                    )
                )

                piece_nom = (
                    "zone non identifiée"
                )

            # ------------------------------------------------
            # Gravité
            # ------------------------------------------------

            score = calculer_score_gravite(
                nom_d,
                ratio_surface,
                conf_d,
            )

            niveau_calcule = (
                score_vers_gravite(
                    score
                )
            )

            if gravite_classe is not None:

                niveau = (
                    gravite_classe
                )

            else:

                niveau = (
                    niveau_calcule
                )

            # ------------------------------------------------
            # Zone critique
            # ------------------------------------------------

            zone_overlap = (
                calculer_overlap_zone_critique(
                    mask_d_np,
                    res_z,
                )
            )

            zone_critique_detectee = (
                nom_d == "d_bosse"
                and zone_overlap
                >= seuil_zone_critique
            )

            if zone_critique_detectee:

                niveau = "high"

            # ------------------------------------------------
            # Coût initial
            # ------------------------------------------------

            if piece_ai_brut is not None:

                detail_cout = (
                    calculer_cout_dommage(
                        piece_ai_brut,
                        nom_d,
                        niveau,
                    )
                )

            else:

                detail_cout = {
                    "avertissement": (
                        "Pièce non identifiée "
                        "avec certitude — "
                        "chiffrage impossible "
                        "automatiquement."
                    ),
                    "total": None,
                }

            # ------------------------------------------------
            # Création de l'instance
            # ------------------------------------------------

            item = {
                "type": (
                    nom_d
                    .replace(
                        "d_",
                        "",
                    )
                    .replace(
                        "_",
                        " ",
                    )
                ),

                "type_brut": nom_d,

                "classe_ia": nom_d_ia,

                "gravite_classe_ia": (
                    gravite_classe
                ),

                "piece_ai_brut": (
                    piece_ai_brut
                ),

                "position_bucket": (
                    bucket
                ),

                "source_image": (
                    nom_image
                ),

                "confiance": conf_d,

                "piece": piece_nom,

                "surface_pct": (
                    ratio_surface * 100
                ),

                "score": score,

                "niveau": niveau,

                "solution": SOLUTIONS.get(
                    nom_d,
                    "À vérifier par un expert",
                ),

                # Proposition initiale de l'IA. Elle est remplacée par
                # action_finale uniquement si l'expert corrige l'action.
                "action_ia": "reparation",
                "action_experte": "",
                "action_finale": "reparation",

                "cout": detail_cout.get(
                    "total"
                ),

                "cout_detail": (
                    detail_cout
                ),

                "n_vues": 1,

                "images_sources": [
                    nom_image
                ],

                "remplacement_requis": False,

                "chiffrage_bloque": False,

                "zone_critique_detectee": (
                    zone_critique_detectee
                ),

                "zone_critique_overlap_pct": (
                    zone_overlap * 100
                ),

                # ==========================================
                # VALIDATION EXPERT
                # ==========================================

                "validation_expert": (
                    "a_valider"
                ),

                "feedback_raison": "",

                "feedback_observation": "",

                "piece_corrigee": "",

                "dommage_corrige": "",

                # Rempli plus tard après déduplication
                "detection_id": None,

                # Version du modèle
                "model_version": "unknown",
            }

            instances.append(item)

    # ======================================================
    # NOMBRE DE ZONES CRITIQUES
    # ======================================================

    n_zones_critiques = (
        len(res_z.boxes)
        if (
            res_z is not None
            and res_z.boxes is not None
        )
        else 0
    )

    return {
        "instances": instances,

        "n_pieces": (
            len(res_p.boxes)
            if res_p.boxes is not None
            else 0
        ),

        "n_dommages": (
            len(res_d.boxes)
            if res_d.boxes is not None
            else 0
        ),

        "n_zones_critiques": (
            n_zones_critiques
        ),

        "img_pieces": (
            res_p.plot()[:, :, ::-1]
        ),

        "img_dommages": (
            res_d.plot()[:, :, ::-1]
        ),

        "img_zones_critiques": (
            res_z.plot()[:, :, ::-1]
            if res_z is not None
            else None
        ),
    }


# ============================================================
# 15. AGRÉGATS
# ============================================================

def calculer_agregats(
    instances: list,
) -> dict:
    """
    Calcule les totaux après application des règles métier.

    IMPORTANT :
    les détections rejetées par l'expert sont totalement
    exclues des calculs financiers.

    Elles restent néanmoins dans instances pour le feedback.
    """

    # ======================================================
    # Initialisation
    # ======================================================

    n_valides = 0
    n_rejetees = 0
    n_a_valider = 0

    for item in instances:

        validation = normaliser_validation(
            item.get(
                "validation_expert"
            )
        )

        if validation == "acceptee":
            n_valides += 1

        elif validation == "rejetee":
            n_rejetees += 1

        else:
            n_a_valider += 1

    # ======================================================
    # Instances utilisables pour le chiffrage
    # ======================================================

    instances_chiffrables = [
        item
        for item in instances
        if detection_valide_pour_chiffrage(
            item
        )
    ]

    # ======================================================
    # Score global
    # ======================================================

    score_global = (
        float(
            np.mean(
                [
                    it.get(
                        "score",
                        0.0,
                    )
                    for it in instances_chiffrables
                ]
            )
        )
        if instances_chiffrables
        else 0.0
    )

    # ======================================================
    # Coût total
    # ======================================================

    cout_total = sum(
        float(
            it.get(
                "cout"
            )
            or 0.0
        )
        for it in instances_chiffrables
        if it.get("cout") is not None
    )

    # ======================================================
    # Éléments à vérifier
    # ======================================================

    n_a_verifier = 0

    for it in instances_chiffrables:

        if it.get(
            "chiffrage_bloque"
        ) is True:

            continue

        if (
            it.get(
                "remplacement_requis"
            ) is True
            and it.get(
                "cout"
            ) is None
        ):

            n_a_verifier += 1

            continue

        if it.get(
            "cout"
        ) is None:

            n_a_verifier += 1

    # ======================================================
    # MO réparation
    # ======================================================

    total_mo_reparation = sum(
        (
            it.get(
                "cout_detail"
            )
            or {}
        ).get(
            "cout_reparation",
            0,
        )
        or 0
        for it in instances_chiffrables
        if it.get(
            "cout"
        ) is not None
    )

    # ======================================================
    # MO peinture
    # ======================================================

    total_mo_peinture = sum(
        (
            it.get(
                "cout_detail"
            )
            or {}
        ).get(
            "cout_mop",
            0,
        )
        or 0
        for it in instances_chiffrables
        if it.get(
            "cout"
        ) is not None
    )

    # ======================================================
    # Produit peinture
    # ======================================================

    total_produit_peinture = sum(
        (
            it.get(
                "cout_detail"
            )
            or {}
        ).get(
            "cout_met",
            0,
        )
        or 0
        for it in instances_chiffrables
        if it.get(
            "cout"
        ) is not None
    )

    # ======================================================
    # Main d'œuvre remplacement
    # ======================================================

    total_mot = sum(
        it.get(
            "cout_mot"
        )
        or 0
        for it in instances_chiffrables
        if it.get(
            "remplacement_requis"
        ) is True
    )

    # ======================================================
    # Fourniture
    # ======================================================

    total_fourniture = sum(
        it.get(
            "prix_piece"
        )
        or 0
        for it in instances_chiffrables
        if it.get(
            "remplacement_requis"
        ) is True
    )

    # ======================================================
    # Résultat
    # ======================================================

    return {
        "score_global": score_global,

        "cout_total": cout_total,

        "n_a_verifier": n_a_verifier,

        "total_mo_reparation": (
            total_mo_reparation
        ),

        "total_mo_peinture": (
            total_mo_peinture
        ),

        "total_produit_peinture": (
            total_produit_peinture
        ),

        "total_mot": total_mot,

        "total_fourniture": (
            total_fourniture
        ),

        # ==============================================
        # VALIDATION EXPERT
        # ==============================================

        "n_valides": n_valides,

        "n_rejetees": n_rejetees,

        "n_a_valider": n_a_valider,

        "n_total_detections": len(
            instances
        ),

        "n_chiffrables": len(
            instances_chiffrables
        ),
    }


# ============================================================
# 16. DÉDUPLICATION
# ============================================================

def dedupliquer_instances(
    toutes_instances: list,
) -> list:
    """
    Déduplique les dommages détectés.

    Règle :
        même pièce + même type de dommage
        =
        un seul dommage retenu.

    La détection ayant la meilleure confiance est conservée.

    Les pièces non identifiées ne sont pas fusionnées.

    Après déduplication, chaque instance reçoit un detection_id
    déterministe utilisé par le système de feedback.
    """

    groupes = {}

    # ======================================================
    # GROUPEMENT
    # ======================================================

    for index, inst in enumerate(
        toutes_instances
    ):

        # --------------------------------------------------
        # Pièce non identifiée
        # --------------------------------------------------

        if (
            inst.get(
                "piece_ai_brut"
            )
            is None
        ):

            # On conserve chaque détection séparément.
            cle = (
                "__unique__",
                index,
            )

        # --------------------------------------------------
        # Pièce identifiée
        # --------------------------------------------------

        else:

            cle = (
                inst.get(
                    "piece_ai_brut"
                ),
                inst.get(
                    "type_brut"
                ),
            )

        groupes.setdefault(
            cle,
            [],
        ).append(inst)

    resultat = []

    # ======================================================
    # SÉLECTION DU REPRÉSENTANT
    # ======================================================

    for membres in (
        groupes.values()
    ):

        representant = max(
            membres,
            key=lambda x: x.get(
                "confiance",
                0.0,
            ),
        ).copy()

        # --------------------------------------------------
        # Nombre de vues
        # --------------------------------------------------

        representant[
            "n_vues"
        ] = len(membres)

        # --------------------------------------------------
        # Images sources
        # --------------------------------------------------

        representant[
            "images_sources"
        ] = sorted(
            {
                m.get(
                    "source_image",
                    "",
                )
                for m in membres
                if m.get(
                    "source_image"
                )
            }
        )

        # --------------------------------------------------
        # Confiance
        # --------------------------------------------------

        representant[
            "confiance_max"
        ] = representant.get(
            "confiance",
            0.0,
        )

        representant[
            "n_detections_fusionnees"
        ] = len(membres) - 1

        # --------------------------------------------------
        # Zone critique
        # --------------------------------------------------

        if (
            representant.get(
                "type_brut"
            )
            == "d_bosse"
            and any(
                m.get(
                    "zone_critique_detectee"
                )
                for m in membres
            )
        ):

            representant[
                "zone_critique_detectee"
            ] = True

            representant[
                "zone_critique_overlap_pct"
            ] = max(
                m.get(
                    "zone_critique_overlap_pct",
                    0.0,
                )
                for m in membres
            )

            representant[
                "niveau"
            ] = "high"

        # --------------------------------------------------
        # Validation
        #
        # Pour l'instant les nouvelles détections sont
        # 'a_valider'.
        # --------------------------------------------------

        initialiser_validation(
            representant
        )

        # --------------------------------------------------
        # detection_id stable
        # --------------------------------------------------

        representant[
            "detection_id"
        ] = generer_detection_id(
            representant
        )

        resultat.append(
            representant
        )

    return resultat


# ============================================================
# 17. STATISTIQUES FEEDBACK
# ============================================================

def statistiques_feedback(
    instances: list,
) -> dict:
    """
    Retourne des statistiques simples sur les validations expert.

    Utile plus tard pour le dashboard de qualité du modèle.
    """

    total = len(instances)

    acceptees = sum(
        1
        for item in instances
        if detection_acceptee(item)
    )

    rejetees = sum(
        1
        for item in instances
        if detection_rejetee(item)
    )

    a_valider = sum(
        1
        for item in instances
        if detection_a_valider(item)
    )

    taux_rejet = (
        rejetees / total * 100
        if total
        else 0.0
    )

    return {
        "total": total,
        "acceptees": acceptees,
        "rejetees": rejetees,
        "a_valider": a_valider,
        "taux_rejet_pct": round(
            taux_rejet,
            2,
        ),
    }