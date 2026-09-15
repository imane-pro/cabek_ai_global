from pathlib import Path
from datetime import datetime
import json
import uuid
import shutil


# ============================================================
# CHEMIN ABSOLU DU PROJET
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DOSSIERS_DIR = PROJECT_ROOT / "data" / "dossiers"

DOSSIERS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# VUES
# ============================================================

VIEWS = {
    "avant": "Vue avant",
    "arriere": "Vue arrière",
    "gauche": "Vue gauche",
    "droite": "Vue droite",
    "details": "Détails des dommages",
}


# ============================================================
# OUTILS
# ============================================================

def dossier_path(dossier_id: str) -> Path:
    return DOSSIERS_DIR / dossier_id


def metadata_path(dossier_id: str) -> Path:
    return dossier_path(dossier_id) / "metadata.json"


# ============================================================
# CREATION DOSSIER
# ============================================================

def create_dossier(
    marque: str,
    matricule: str,
    modele: str = "",
    expert: str = "",
    annee: str = "",
    type_vehicule: str = "Particulier",
):

    maintenant = datetime.now()

    dossier_id = (
        f"DOS-{maintenant.strftime('%Y%m%d-%H%M%S')}-"
        f"{uuid.uuid4().hex[:6].upper()}"
    )

    folder = dossier_path(dossier_id)
    photos_dir = folder / "photos"

    folder.mkdir(parents=True, exist_ok=True)
    photos_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "dossier_id": dossier_id,
        "marque": marque.strip(),
        "modele": modele.strip(),
        "matricule": matricule.strip(),
        "expert": expert.strip(),
        "annee": annee.strip(),
        "type_vehicule": type_vehicule,
        "date_creation": maintenant.isoformat(),
        "statut": "Brouillon",
        "photos": [],
    }

    with open(
        metadata_path(dossier_id),
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            metadata,
            f,
            ensure_ascii=False,
            indent=2
        )

    return dossier_id


# ============================================================
# CHARGER METADATA
# ============================================================

def load_metadata(dossier_id: str):

    path = metadata_path(dossier_id)

    if not path.exists():
        raise FileNotFoundError(
            f"Metadata introuvable pour le dossier : {dossier_id}"
        )

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# SAUVEGARDER METADATA
# ============================================================

def save_metadata(dossier_id: str, metadata: dict):

    path = metadata_path(dossier_id)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            metadata,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# PHOTO
# ============================================================

def save_uploaded_photo(
    dossier_id,
    view,
    uploaded_file,
    index=1
):

    folder = dossier_path(dossier_id) / "photos" / view

    folder.mkdir(
        parents=True,
        exist_ok=True
    )

    original_name = getattr(
        uploaded_file,
        "name",
        f"{view}_{index}.jpg"
    )

    extension = Path(original_name).suffix.lower()

    if extension not in [".jpg", ".jpeg", ".png"]:
        extension = ".jpg"

    filename = f"{view}_{index:02d}{extension}"

    target = folder / filename

    with open(target, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return str(target)


# ============================================================
# ENREGISTRER PHOTO DANS METADATA
# ============================================================

def register_photo(
    dossier_id,
    view,
    target
):

    metadata = load_metadata(dossier_id)

    photos = metadata.setdefault(
        "photos",
        []
    )

    target = str(target)

    # Eviter les doublons
    for photo in photos:
        if photo.get("path") == target:
            return

    photos.append({
        "view": view,
        "path": target,
        "filename": Path(target).name,
        "date": datetime.now().isoformat(),
    })

    save_metadata(
        dossier_id,
        metadata
    )


# ============================================================
# STATUT
# ============================================================

def set_status(
    dossier_id,
    status
):

    metadata = load_metadata(dossier_id)

    metadata["statut"] = status

    save_metadata(
        dossier_id,
        metadata
    )