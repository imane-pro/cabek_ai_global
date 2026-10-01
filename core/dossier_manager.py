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