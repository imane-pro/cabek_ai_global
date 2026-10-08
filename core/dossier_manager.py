from __future__ import annotations

import json
import re
import uuid

from datetime import datetime
from pathlib import Path
from typing import Dict, List


# ============================================================
# CHEMINS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

DOSSIERS_DIR = ROOT / "data" / "dossiers"

DOSSIERS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# VUES
# ============================================================

VIEWS = {
    "avant": "Vue avant",
    "arriere": "Vue arrière",
    "gauche": "Vue gauche",
    "droite": "Vue droite",
    "details": "Détails dommages",
}


# ============================================================
# NETTOYAGE TEXTE
# ============================================================

def safe_text(value: str) -> str:
    """
    Nettoie un texte afin de pouvoir l'utiliser
    dans un nom de dossier ou de fichier.
    """

    value = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        str(value).strip(),
    )

    return value.strip("_") or "NA"


# ============================================================
# ID DOSSIER
# ============================================================

def new_dossier_id() -> str:
    """
    Génère un identifiant unique pour un dossier.
    """

    return (
        datetime.now().strftime(
            "DOS-%Y%m%d-%H%M%S-"
        )
        + uuid.uuid4().hex[:6].upper()
    )


# ============================================================
# CHEMIN DOSSIER
# ============================================================

def dossier_path(
    dossier_id: str,
) -> Path:
    """
    Retourne le chemin physique d'un dossier.
    """

    return DOSSIERS_DIR / safe_text(
        dossier_id
    )


# ============================================================
# CRÉATION DOSSIER
# ============================================================

def create_dossier(
    marque: str,
    matricule: str,
    modele: str = "",
    annee: str = "",
    marque_id: int | None = None,
    model_id: int | None = None,
    expert: str = "",
) -> str:
    """
    Crée un nouveau dossier d'expertise.
    """

    dossier_id = new_dossier_id()

    path = dossier_path(
        dossier_id
    )

    (
        path / "photos"
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata = {

        # ----------------------------------------------------
        # IDENTIFICATION DOSSIER
        # ----------------------------------------------------

        "dossier_id": dossier_id,

        # ----------------------------------------------------
        # VÉHICULE
        # ----------------------------------------------------

        "marque": marque.strip(),

        "marque_id": marque_id,

        "modele": modele.strip(),

        "model_id": model_id,

        "annee": annee.strip(),

        "matricule": matricule.strip().upper(),

        # ----------------------------------------------------
        # EXPERT
        # ----------------------------------------------------

        "expert": expert.strip(),

        # ----------------------------------------------------
        # DOSSIER
        # ----------------------------------------------------

        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),

        "status": "Brouillon",

        # ----------------------------------------------------
        # PHOTOS
        # ----------------------------------------------------

        "photos": [],
    }

    save_metadata(
        path,
        metadata,
    )

    return dossier_id


# ============================================================
# SAUVEGARDE METADATA
# ============================================================

def save_metadata(
    path: Path,
    metadata: Dict,
) -> None:
    """
    Sauvegarde le metadata.json du dossier.
    """

    (
        path / "metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# CHARGER METADATA
# ============================================================

def load_metadata(
    dossier_id: str,
) -> Dict:
    """
    Charge les informations du dossier.
    """

    path = dossier_path(
        dossier_id
    )

    file = path / "metadata.json"

    if not file.exists():

        raise FileNotFoundError(
            f"Dossier introuvable : {dossier_id}"
        )

    return json.loads(
        file.read_text(
            encoding="utf-8"
        )
    )


# ============================================================
# SAUVEGARDER PHOTO
# ============================================================

def save_uploaded_photo(
    dossier_id: str,
    view_key: str,
    uploaded_file,
    index: int = 1,
) -> Path:
    """
    Sauvegarde une photo uploadée dans le dossier.
    """

    if view_key not in VIEWS:

        raise ValueError(
            f"Vue inconnue : {view_key}"
        )

    path = (
        dossier_path(dossier_id)
        / "photos"
    )

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    suffix = (
        Path(uploaded_file.name)
        .suffix
        .lower()
        or ".jpg"
    )

    filename = (
        f"{view_key}_{index:02d}{suffix}"
    )

    target = path / filename

    target.write_bytes(
        uploaded_file.getvalue()
    )

    return target


# ============================================================
# ENREGISTRER PHOTO DANS METADATA
# ============================================================

def register_photo(
    dossier_id: str,
    view_key: str,
    file_path: Path,
) -> None:
    """
    Ajoute une photo dans metadata.json.
    """

    metadata = load_metadata(
        dossier_id
    )

    dossier_dir = dossier_path(
        dossier_id
    )

    relative_path = str(
        file_path.relative_to(
            dossier_dir
        )
    )

    photos = [
        p
        for p in metadata.get(
            "photos",
            [],
        )
        if p.get("path") != relative_path
    ]

    photos.append(
        {
            "view": view_key,
            "view_label": VIEWS[view_key],
            "filename": file_path.name,
            "path": relative_path,
        }
    )

    metadata["photos"] = photos

    save_metadata(
        dossier_dir,
        metadata,
    )


# ============================================================
# CHANGER STATUS
# ============================================================

def set_status(
    dossier_id: str,
    status: str,
) -> None:
    """
    Modifie le statut du dossier.
    """

    metadata = load_metadata(
        dossier_id
    )

    metadata["status"] = status

    metadata["updated_at"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    save_metadata(
        dossier_path(dossier_id),
        metadata,
    )


# ============================================================
# LISTE DES DOSSIERS
# ============================================================

def list_dossiers() -> List[Dict]:
    """
    Retourne la liste des dossiers disponibles.
    """

    result = []

    for folder in sorted(
        DOSSIERS_DIR.iterdir(),
        reverse=True,
    ):

        if (
            not folder.is_dir()
            or not (
                folder / "metadata.json"
            ).exists()
        ):
            continue

        try:

            result.append(
                json.loads(
                    (
                        folder
                        / "metadata.json"
                    ).read_text(
                        encoding="utf-8"
                    )
                )
            )

        except Exception:

            continue

    return result


# ============================================================
# CHEMINS DES PHOTOS
# ============================================================

def photo_paths(
    dossier_id: str,
) -> List[Dict]:
    """
    Retourne les photos physiques
    associées au dossier.
    """

    metadata = load_metadata(
        dossier_id
    )

    base = dossier_path(
        dossier_id
    )

    result = []

    for p in metadata.get(
        "photos",
        [],
    ):

        full = (
            base / p["path"]
        )

        if full.exists():

            result.append(
                {
                    **p,
                    "full_path": full,
                }
            )

    return result


# ============================================================
# FEEDBACK IA / VALIDATION EXPERT
# ============================================================

def feedback_path(
    dossier_id: str,
) -> Path:
    """
    Retourne le chemin du fichier feedback.json
    du dossier.
    """

    return (
        dossier_path(dossier_id)
        / "feedback.json"
    )


# ============================================================
# CHARGER FEEDBACK
# ============================================================

def load_feedback(
    dossier_id: str,
) -> List[Dict]:
    """
    Charge tous les feedbacks du dossier.

    Si le fichier n'existe pas ou s'il est invalide,
    une liste vide est retournée.
    """

    path = feedback_path(
        dossier_id
    )

    if not path.exists():
        return []

    try:

        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            data,
            list,
        ):
            return []

        return data

    except Exception:

        return []


# ============================================================
# SAUVEGARDER FEEDBACK
# ============================================================

def save_feedback(
    dossier_id: str,
    feedback: Dict,
) -> None:
    """
    Ajoute un feedback expert au dossier.

    Le feedback est conservé afin de permettre
    l'analyse des erreurs et le futur réentraînement
    des modèles IA.
    """

    path = feedback_path(
        dossier_id
    )

    feedbacks = load_feedback(
        dossier_id
    )

    feedbacks.append(
        feedback
    )

    path.write_text(
        json.dumps(
            feedbacks,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# CRÉER FEEDBACK
# ============================================================

def create_feedback(
    dossier_id: str,
    item: Dict,
    validation: str,
    raison: str = "",
    observation: str = "",
    expert: str = "",
    correction_piece: str = "",
    correction_dommage: str = "",
) -> Dict:
    """
    Construit et sauvegarde un feedback humain.

    validation peut être :

        acceptee
        rejetee
        corrigee
    """

    feedback = {

        # ----------------------------------------------------
        # IDENTIFICATION FEEDBACK
        # ----------------------------------------------------

        "feedback_id": str(
            uuid.uuid4()
        ),

        "dossier_id": dossier_id,

        "created_at": (
            datetime.now().isoformat(
                timespec="seconds"
            )
        ),

        "expert": expert,

        # ----------------------------------------------------
        # IDENTIFICATION DÉTECTION
        # ----------------------------------------------------

        "detection_id": item.get(
            "detection_id"
        ),

        # ----------------------------------------------------
        # PRÉDICTION PIÈCE
        # ----------------------------------------------------

        "piece_predite": item.get(
            "piece_ai_brut"
        ),

        "piece_affichee": item.get(
            "piece"
        ),

        # ----------------------------------------------------
        # PRÉDICTION DOMMAGE
        # ----------------------------------------------------

        "dommage_predit": item.get(
            "type_brut"
        ),

        "classe_ia": item.get(
            "classe_ia"
        ),

        "confiance": item.get(
            "confiance"
        ),

        # ----------------------------------------------------
        # IMAGE
        # ----------------------------------------------------

        "source_image": item.get(
            "source_image"
        ),

        "images_sources": item.get(
            "images_sources",
            [],
        ),

        # ----------------------------------------------------
        # VALIDATION EXPERT
        # ----------------------------------------------------

        "validation": validation,

        "raison": raison,

        "observation": observation,

        # ----------------------------------------------------
        # CORRECTION EXPERT
        # ----------------------------------------------------

        "piece_corrigee": (
            correction_piece
        ),

        "dommage_corrige": (
            correction_dommage
        ),

        # ----------------------------------------------------
        # VERSION MODÈLE
        # ----------------------------------------------------

        "model_version": item.get(
            "model_version",
            "unknown",
        ),
    }

    save_feedback(
        dossier_id,
        feedback,
    )

    return feedback