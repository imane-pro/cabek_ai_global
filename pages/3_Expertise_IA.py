import io
import time
import json
import base64
from pathlib import Path
from datetime import datetime

import numpy as np
import streamlit as st
from PIL import Image
from ultralytics import YOLO

from core.ui import header

from core.dossier_manager import (
    list_dossiers,
    load_metadata,
    photo_paths,
    set_status,
    load_feedback,
    save_feedback,
)

from core.expertise_engine import (
    analyser,
    dedupliquer_instances,
    appliquer_priorite_remplacement,
    calculer_agregats,
    calculer_detail_fourniture,
    LABEL_GRAVITE,
    enrichir_prix_pieces,
    item_key,
    appliquer_feedback_aux_instances,
    appliquer_validation_acceptee,
    appliquer_validation_rejetee,
    detection_a_valider,
    detection_acceptee,
    detection_rejetee,
    statistiques_feedback,
)

from core.parts_pricing import TYPES_PIECE_API

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)


# ============================================================
# CONFIGURATION
# ============================================================

# IMPORTANT :
# st.set_page_config() ne doit PAS être appelé ici
# car l'application principale app.py le fait déjà.


# ============================================================
# OUTILS
# ============================================================

def html(content: str) -> str:
    """
    Nettoie l'indentation HTML pour éviter que Streamlit
    interprète certaines parties comme du Markdown.
    """

    lines = (
        line.strip()
        for line in content.strip("\n").splitlines()
    )

    return "\n".join(
        line for line in lines
        if line
    )


def file_to_data_uri(path) -> str:
    """
    Transforme une image locale en Data URI.
    """

    path = Path(path)

    data = path.read_bytes()

    ext = path.suffix.lower().lstrip(".")

    mime = (
        "jpeg"
        if ext in ("jpg", "jpeg")
        else ext
    )

    return (
        f"data:image/{mime};base64,"
        f"{base64.b64encode(data).decode()}"
    )


def array_to_data_uri(
    arr,
    fmt="JPEG",
) -> str:
    """
    Transforme une image numpy en Data URI.
    """

    buffer = io.BytesIO()

    Image.fromarray(arr).save(
        buffer,
        format=fmt,
    )

    mime = (
        "jpeg"
        if fmt.upper() == "JPEG"
        else fmt.lower()
    )

    return (
        f"data:image/{mime};base64,"
        f"{base64.b64encode(buffer.getvalue()).decode()}"
    )


@st.cache_resource(show_spinner=False)
def load_model(path: str):
    """
    Charge un modèle YOLO une seule fois.
    """

    return YOLO(path)


# ============================================================
# STATUTS DOSSIER
# ============================================================

STATUS_CLASSES = {
    "Validé": "status-green",
    "Envoyé": "status-orange",
    "En analyse": "status-orange",
    "À valider": "status-orange",
    "Brouillon": "status-gray",
    "Créé": "status-gray",
}


def status_class(status: str) -> str:
    return STATUS_CLASSES.get(
        status,
        "status-blue",
    )


# ============================================================
# COMPOSANTS UI
# ============================================================

def section_header(
    title: str,
    subtitle: str = "",
):
    subtitle_html = ""

    if subtitle:
        subtitle_html = (
            f'<div class="section-subtitle">'
            f'{subtitle}'
            f'</div>'
        )

    st.markdown(
        html(
            f"""
            <div class="section-header">

                <div class="section-title">
                    {title}
                </div>

                {subtitle_html}

            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def render_kpi(
    col,
    icon,
    label,
    value,
    description="",
    variant="",
):
    col.markdown(
        html(
            f"""
            <div class="kpi-card {variant}">

                <div class="kpi-top">

                    <div class="kpi-label">
                        {label}
                    </div>

                    <div class="kpi-icon">
                        {icon}
                    </div>

                </div>

                <div class="kpi-value">
                    {value}
                </div>

                <div class="kpi-description">
                    {description}
                </div>

            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def empty_state(
    icon,
    title,
    description,
):
    st.markdown(
        html(
            f"""
            <div class="empty-state">

                <div class="empty-icon">
                    {icon}
                </div>

                <div class="empty-title">
                    {title}
                </div>

                <div class="empty-description">
                    {description}
                </div>

            </div>
            """
        ),
        unsafe_allow_html=True,
    )


# ============================================================
# FEEDBACK
# ============================================================

def upsert_feedback_local(
    dossier_id: str,
    feedback: dict,
):
    """
    Sauvegarde ou met à jour le feedback d'une détection.

    On utilise detection_id comme clé stable afin d'éviter
    de créer plusieurs feedbacks pour la même détection.
    """

    feedbacks = load_feedback(dossier_id)

    detection_id = feedback.get(
        "detection_id"
    )

    replaced = False

    for index, existing in enumerate(feedbacks):

        if (
            detection_id
            and existing.get("detection_id")
            == detection_id
        ):
            feedbacks[index] = feedback
            replaced = True
            break

    if not replaced:
        feedbacks.append(feedback)

    # Le gestionnaire de dossier ajoute un seul feedback à la fois.
    # Pour remplacer un feedback existant, on réécrit directement le fichier.
    from core.dossier_manager import feedback_path

    feedback_path(dossier_id).write_text(
        json.dumps(
            feedbacks,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def construire_feedback(
    dossier_id: str,
    item: dict,
    validation: str,
    raison: str = "",
    observation: str = "",
    correction_piece: str = "",
    correction_dommage: str = "",
):
    """
    Construit un feedback complet pour la détection.
    """

    return {
        "feedback_id": (
            f"FB-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        ),

        "dossier_id": dossier_id,

        "created_at": (
            datetime.now().isoformat(
                timespec="seconds"
            )
        ),

        "detection_id": item.get(
            "detection_id"
        ),

        "piece_predite": item.get(
            "piece_ai_brut"
        ),

        "piece_affichee": item.get(
            "piece"
        ),

        "dommage_predit": item.get(
            "type_brut"
        ),

        "classe_ia": item.get(
            "classe_ia"
        ),

        "confiance": item.get(
            "confiance"
        ),

        "source_image": item.get(
            "source_image"
        ),

        "images_sources": item.get(
            "images_sources",
            [],
        ),

        "validation": validation,

        "raison": raison,

        "observation": observation,

        "piece_corrigee": correction_piece,

        "dommage_corrige": correction_dommage,

        "model_version": item.get(
            "model_version",
            "unknown",
        ),
    }


def recalculer_analysis():
    """
    Recalcule les règles métier + agrégats après une validation.
    """

    instances = st.session_state.analysis[
        "instances"
    ]

    instances = appliquer_priorite_remplacement(
        instances
    )

    ag = calculer_agregats(
        instances
    )

    st.session_state.analysis[
        "instances"
    ] = instances

    st.session_state.analysis[
        "ag"
    ] = ag


def pending_count(instances):
    """
    Nombre de détections encore à valider par l'expert.
    """

    return sum(
        1
        for item in instances
        if detection_a_valider(item)
    )


# ============================================================
# CSS
# ============================================================

st.markdown(
    html(
        """
        <style>

        .block-container {
            max-width: 1450px;
            padding-top: 1.5rem;
            padding-bottom: 4rem;
        }

        /* =====================================================
           DOSSIER HEADER
        ===================================================== */

        .dossier-header {
            background:
                linear-gradient(
                    135deg,
                    #071b38 0%,
                    #0d3970 55%,
                    #175fc7 100%
                );

            border-radius: 18px;
            padding: 25px 28px;
            color: white;
            position: relative;
            overflow: hidden;
            margin-bottom: 20px;
        }

        .dossier-header::after {
            content: "";
            position: absolute;
            width: 260px;
            height: 260px;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 50%;
            right: -90px;
            top: -100px;
        }

        .dossier-eyebrow {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: .08em;
            color: #9fc5ef;
            font-weight: 800;
        }

        .dossier-title {
            font-size: 27px;
            font-weight: 900;
            margin-top: 5px;
        }

        .dossier-subtitle {
            margin-top: 7px;
            color: #c4d7ed;
            font-size: 12px;
        }

        .status-pill {
            display: inline-block;
            margin-top: 12px;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 10px;
            font-weight: 800;
        }

        .status-green {
            background: rgba(22,184,121,.18);
            border: 1px solid rgba(22,184,121,.4);
            color: #a9f4d6;
        }

        .status-orange {
            background: rgba(240,162,26,.18);
            border: 1px solid rgba(240,162,26,.4);
            color: #ffdf9e;
        }

        .status-blue {
            background: rgba(22,119,255,.18);
            border: 1px solid rgba(22,119,255,.4);
            color: #bcdcff;
        }

        .status-gray {
            background: rgba(255,255,255,.10);
            border: 1px solid rgba(255,255,255,.25);
            color: #d6dde6;
        }

        /* =====================================================
           WORKFLOW
        ===================================================== */

        .workflow {
            display: flex;
            gap: 8px;
            margin: 18px 0 25px 0;
        }

        .workflow-item {
            flex: 1;
            background: #ffffff;
            border: 1px solid #e1e7ef;
            border-radius: 12px;
            padding: 12px;
            min-height: 70px;
        }

        .workflow-item.done {
            border-color: #b9e7d3;
            background: #f2fbf7;
        }

        .workflow-item.active {
            border-color: #1769d5;
            background: #eef6ff;
        }

        .workflow-number {
            width: 27px;
            height: 27px;
            border-radius: 50%;
            background: #e7edf4;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            font-size: 11px;
            color: #526173;
            margin-bottom: 6px;
        }

        .workflow-item.done .workflow-number {
            background: #16b879;
            color: white;
        }

        .workflow-item.active .workflow-number {
            background: #1769d5;
            color: white;
        }

        .workflow-title {
            font-size: 11px;
            font-weight: 850;
            color: #172235;
        }

        .workflow-state {
            font-size: 9px;
            color: #8491a3;
            margin-top: 2px;
        }

        /* =====================================================
           KPI
        ===================================================== */

        .kpi-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 17px;
            min-height: 112px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 3px 14px rgba(15,35,60,.045);
        }

        .kpi-card::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
            background: #1769d5;
        }

        .kpi-card.green::before {
            background: #16b879;
        }

        .kpi-card.orange::before {
            background: #f0a21a;
        }

        .kpi-card.red::before {
            background: #dc3545;
        }

        .kpi-card.dark::before {
            background: #344054;
        }

        .kpi-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .kpi-label {
            font-size: 10px;
            font-weight: 800;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: .04em;
        }

        .kpi-icon {
            width: 29px;
            height: 29px;
            border-radius: 9px;
            background: #edf5ff;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .kpi-value {
            margin-top: 10px;
            font-size: 23px;
            font-weight: 900;
            color: #162033;
        }

        .kpi-description {
            margin-top: 5px;
            font-size: 9px;
            color: #8995a6;
        }

        /* =====================================================
           SECTION
        ===================================================== */

        .section-header {
            margin-top: 22px;
            margin-bottom: 12px;
        }

        .section-title {
            font-size: 17px;
            font-weight: 900;
            color: #172235;
        }

        .section-subtitle {
            font-size: 11px;
            color: #8491a3;
            margin-top: 3px;
        }

        /* =====================================================
           INFO
        ===================================================== */

        .info-banner {
            background: #f5f9fd;
            border: 1px solid #dce7f2;
            border-radius: 12px;
            padding: 13px 16px;
            color: #526173;
            font-size: 11px;
            line-height: 1.55;
            margin: 10px 0 18px 0;
        }

        /* =====================================================
           EMPTY
        ===================================================== */

        .empty-state {
            text-align: center;
            padding: 45px 20px;
            background: #fafbfd;
            border: 1px dashed #d5dee9;
            border-radius: 15px;
            margin: 15px 0;
        }

        .empty-icon {
            font-size: 35px;
            margin-bottom: 10px;
        }

        .empty-title {
            font-size: 15px;
            font-weight: 850;
            color: #344054;
        }

        .empty-description {
            margin-top: 5px;
            font-size: 11px;
            color: #8995a6;
        }

        /* =====================================================
           PHOTO
        ===================================================== */

        .photo-card {
            background: #ffffff;
            border: 1px solid #e3e8ef;
            border-radius: 13px;
            padding: 10px;
            margin-bottom: 14px;
            box-shadow: 0 2px 8px rgba(15,35,60,.04);
        }

        .photo-title {
            margin-top: 8px;
            font-size: 11px;
            font-weight: 850;
            color: #172235;
        }

        .photo-filename {
            font-size: 9px;
            color: #99a3b1;
            margin-top: 2px;
        }

        .photo-img {
            width: 100%;
            max-height: 470px;
            object-fit: contain;
            border-radius: 9px;
            background: #f4f6f8;
        }

        /* =====================================================
           DAMAGE CARD
        ===================================================== */

        .damage-card {
            background: #ffffff;
            border: 1px solid #e4e9ef;
            border-radius: 13px;
            padding: 16px;
            margin-bottom: 12px;
            box-shadow: 0 2px 9px rgba(15,35,60,.035);
        }

        .damage-title {
            font-size: 15px;
            font-weight: 850;
            color: #172235;
        }

        .damage-meta {
            margin-top: 5px;
            font-size: 10px;
            color: #718096;
        }

        .sev-pill {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 9px;
            font-weight: 850;
        }

        /* =====================================================
           VALIDATION
        ===================================================== */

        .validation-card {
            background: #f2fbf7;
            border: 1px solid #bfe9d6;
            border-radius: 14px;
            padding: 18px;
            margin-bottom: 18px;
        }

        .validation-card.warning {
            background: #fff8e8;
            border-color: #f3d58a;
        }

        .validation-card.danger {
            background: #fff1f2;
            border-color: #f1b8bd;
        }

        .validation-title {
            font-size: 15px;
            font-weight: 850;
            color: #145c40;
        }

        .validation-card.warning .validation-title {
            color: #7a5700;
        }

        .validation-card.danger .validation-title {
            color: #9f1c26;
        }

        .validation-text {
            font-size: 11px;
            color: #557466;
            margin-top: 5px;
        }

        /* =====================================================
           FEEDBACK
        ===================================================== */

        .feedback-pending {
            background: #fff8e8;
            border: 1px solid #f3d58a;
            border-radius: 10px;
            padding: 10px 12px;
            margin-top: 10px;
        }

        .feedback-ok {
            background: #effaf4;
            border: 1px solid #b9e7d3;
            border-radius: 10px;
            padding: 10px 12px;
            margin-top: 10px;
        }

        .feedback-rejected {
            background: #fff1f2;
            border: 1px solid #f1b8bd;
            border-radius: 10px;
            padding: 10px 12px;
            margin-top: 10px;
        }

        /* =====================================================
           PRICE
        ===================================================== */

        .price-card {
            background: #f7fbff;
            border: 1px solid #d7e9fb;
            border-radius: 14px;
            padding: 18px;
            margin-bottom: 15px;
        }

        .price-title {
            font-size: 14px;
            font-weight: 850;
            color: #172235;
        }

        .price-value {
            font-size: 25px;
            font-weight: 900;
            color: #0c3158;
            margin-top: 6px;
        }

        .price-meta {
            font-size: 10px;
            color: #718096;
            margin-top: 4px;
        }

        /* =====================================================
           VISUALISATION
        ===================================================== */

        .viz-img {
            width: 100%;
            max-width: 340px;
            border-radius: 9px;
            display: block;
            margin: 0 auto;
        }

        .viz-col-title {
            text-align: center;
            font-size: 11px;
            font-weight: 800;
            color: #172235;
            margin-bottom: 6px;
        }

        </style>
        """
    ),
    unsafe_allow_html=True,
)


# ============================================================
# HEADER
# ============================================================

header(
    "Expertise IA",
    "Analyse, expertise et chiffrage automobile",
)


# ============================================================
# CHARGEMENT DES DOSSIERS
# ============================================================

dossiers = list_dossiers()

if not dossiers:

    empty_state(
        "📂",
        "Aucun dossier disponible",
        "Crée d'abord un dossier depuis « Collecte des données ».",
    )

    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("## 📂 Dossier")

    labels = [
        (
            f"{d.get('dossier_id', '—')} "
            f"· {d.get('matricule', '—')} "
            f"· {d.get('marque', '—')} "
            f"{d.get('modele', '')}"
        )
        for d in dossiers
    ]

    selected_idx = st.selectbox(
        "Sélectionner le dossier",
        range(len(dossiers)),
        format_func=lambda i: labels[i],
        key="expertise_dossier_select",
    )

    selected = dossiers[
        selected_idx
    ]

    st.divider()

    # Les paramètres techniques IA sont volontairement masqués
    # dans l'interface expert. Ils sont fixés dans le code.
    #
    # Seuils utilisés par l'analyse :
    #   - pièces : 50 %
    #   - dommages : 50 %
    #   - zone critique : 25 %
    #   - association dommage ↔ pièce : 0.05
    #   - intersection zone critique : 0.05
    #
    # Les chemins des modèles restent également internes à l'application.

    path_pieces = "models/best_pieces.pt"
    path_dommages = "models/best.pt"
    path_critical = "models/best_zone_critique.pt"

    use_critical = True
    conf_pieces = 0.50
    conf_dommages = 0.50
    conf_critical = 0.25
    iou_min = 0.05
    critical_threshold = 0.05
    dedup = True


# ============================================================
# MÉTADONNÉES
# ============================================================

dossier_id = selected[
    "dossier_id"
]

meta = load_metadata(
    dossier_id
)

photos = photo_paths(
    dossier_id
)


# ============================================================
# RESET ANALYSE SI CHANGEMENT DOSSIER
# ============================================================

analysis = st.session_state.get(
    "analysis"
)

if (
    analysis is not None
    and analysis.get("dossier_id")
    != dossier_id
):

    st.session_state.pop(
        "analysis",
        None,
    )

    analysis = None


has_analysis = (
    analysis is not None
    and analysis.get("dossier_id")
    == dossier_id
)


# ============================================================
# HEADER DOSSIER
# ============================================================

status = meta.get(
    "status",
    "Brouillon",
)

marque = meta.get(
    "marque",
    "—",
)

modele = meta.get(
    "modele",
    "",
)

matricule = meta.get(
    "matricule",
    "—",
)

annee = meta.get(
    "annee",
    "—",
)

st.markdown(
    html(
        f"""
        <div class="dossier-header">

            <div class="dossier-eyebrow">
                DOSSIER D'EXPERTISE ACTIF
            </div>

            <div class="dossier-title">
                {marque} {modele}
            </div>

            <div class="dossier-subtitle">
                Dossier <b>{dossier_id}</b>
                · Matricule <b>{matricule}</b>
                · Mise en circulation <b>{annee}</b>
                · {len(photos)} photo(s)
            </div>

            <span class="status-pill {status_class(status)}">
                {status}
            </span>

        </div>
        """
    ),
    unsafe_allow_html=True,
)


# ============================================================
# WORKFLOW
# ============================================================

ag_courant = (
    analysis.get("ag")
    if has_analysis
    else None
)

pending_current = (
    pending_count(
        analysis["instances"]
    )
    if has_analysis
    else 0
)

step1 = len(photos) > 0
step2 = has_analysis

step3 = (
    has_analysis
    and ag_courant is not None
    and ag_courant.get(
        "n_a_verifier",
        1,
    ) == 0
    and pending_current == 0
)

step4 = has_analysis

step5 = status == "Validé"

workflow = [
    ("1", "Dossier photo", step1),
    ("2", "Analyse & résultats", step2),
    ("3", "Chiffrage", step3),
    ("4", "Contrôle visuel", step4),
    ("5", "Validation & rapport", step5),
]

workflow_html = ""

for number, title, done in workflow:

    cls = (
        "done"
        if done
        else ""
    )

    workflow_html += f"""
        <div class="workflow-item {cls}">

            <div class="workflow-number">
                {"✓" if done else number}
            </div>

            <div class="workflow-title">
                {title}
            </div>

            <div class="workflow-state">
                {"Terminé" if done else "À faire"}
            </div>

        </div>
    """


st.markdown(
    html(
        f"""
        <div class="workflow">
            {workflow_html}
        </div>
        """
    ),
    unsafe_allow_html=True,
)


# ============================================================
# KPI DOSSIER
# ============================================================

k1, k2, k3, k4 = st.columns(4)

render_kpi(
    k1,
    "🚘",
    "Véhicule",
    marque,
    modele or "Modèle non renseigné",
)

render_kpi(
    k2,
    "🔖",
    "Matricule",
    matricule,
    "Identification du véhicule",
    "dark",
)

render_kpi(
    k3,
    "📅",
    "Mise en circulation",
    annee,
    "Année du véhicule",
)

render_kpi(
    k4,
    "📷",
    "Photos",
    len(photos),
    "Photos disponibles",
    "orange",
)


# ============================================================
# ONGLETS
# ============================================================

(
    tab_dossier,
    tab_analyse,
    tab_chiffrage,
    tab_controle,
    tab_rapport,
) = st.tabs(
    [
        "📸 Dossier",
        "🤖 Analyse & résultats",
        "💰 Chiffrage",
        "🖼️ Contrôle visuel",
        "📄 Validation & rapport",
    ]
)


# ============================================================
# ONGLET 1 — DOSSIER
# ============================================================

with tab_dossier:

    section_header(
        "Dossier photo",
        "Vérifie les photos avant de lancer l'intelligence artificielle.",
    )

    if not photos:

        empty_state(
            "📷",
            "Aucune photo disponible",
            "Ajoute les vues principales depuis « Collecte des données ».",
        )

    else:

        st.markdown(
            html(
                """
                <div class="info-banner">

                    <b>Avant de lancer l'analyse :</b>

                    vérifie que les photos avant, arrière,
                    gauche et droite sont présentes et visibles.

                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        section_header(
            "Photo sélectionnée",
            "Utilise la liste pour examiner une vue en détail.",
        )

        photo_labels = [
            (
                f"{p.get('view_label', p.get('view'))}"
                f" · {p['filename']}"
            )
            for p in photos
        ]

        photo_idx = st.selectbox(
            "Vue à consulter",
            range(len(photos)),
            format_func=lambda i: photo_labels[i],
            key="photo_viewer_select",
        )

        selected_photo = photos[
            photo_idx
        ]

        uri = file_to_data_uri(
            selected_photo[
                "full_path"
            ]
        )

        left, center, right = st.columns(
            [1, 2, 1]
        )

        with center:

            st.markdown(
                html(
                    f"""
                    <div class="photo-card">

                        <img
                            src="{uri}"
                            class="photo-img"
                        />

                        <div class="photo-title">
                            {selected_photo.get(
                                'view_label',
                                selected_photo.get('view')
                            )}
                        </div>

                        <div class="photo-filename">
                            {selected_photo['filename']}
                        </div>

                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )

        section_header(
            "Toutes les photos",
            f"{len(photos)} photo(s) enregistrée(s).",
        )

        columns = st.columns(
            min(4, len(photos))
        )

        for index, photo in enumerate(
            photos
        ):

            with columns[
                index % len(columns)
            ]:

                photo_uri = file_to_data_uri(
                    photo["full_path"]
                )

                st.markdown(
                    html(
                        f"""
                        <div class="photo-card">

                            <img
                                src="{photo_uri}"
                                style="
                                    width:100%;
                                    height:150px;
                                    object-fit:contain;
                                    border-radius:8px;
                                    background:#f4f6f8;
                                "
                            />

                            <div class="photo-title">
                                {photo.get(
                                    'view_label',
                                    photo.get('view')
                                )}
                            </div>

                            <div class="photo-filename">
                                {photo['filename']}
                            </div>

                        </div>
                        """
                    ),
                    unsafe_allow_html=True,
                )


# ============================================================
# ONGLET 2 — ANALYSE
# ============================================================

with tab_analyse:

    section_header(
        "Analyse IA",
        "Détection des pièces, dommages, zones critiques et règles métier.",
    )

    st.markdown(
        html(
            """
            <div class="info-banner">

                <b>Pipeline CABEK.AI</b><br>

                ① Détection pièces
                →
                ② Détection dommages
                →
                ③ Association dommage / pièce
                →
                ④ Zone critique
                →
                ⑤ Règles métier
                →
                ⑥ Fusion des vues
                →
                ⑦ Validation expert

            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    # ========================================================
    # LANCEMENT ANALYSE
    # ========================================================

    if not photos:

        st.warning(
            "Impossible de lancer l'analyse : "
            "aucune photo n'est disponible."
        )

    else:

        launch = st.button(
            "🚀 Lancer / relancer l'analyse IA",
            type="primary",
            use_container_width=True,
        )

        if launch:

            try:

                with st.spinner(
                    "Chargement des modèles IA..."
                ):

                    model_p = load_model(
                        path_pieces
                    )

                    model_d = load_model(
                        path_dommages
                    )

                    model_z = (
                        load_model(
                            path_critical
                        )
                        if use_critical
                        else None
                    )

                set_status(
                    dossier_id,
                    "En analyse",
                )

                all_results = []

                start_time = time.time()

                progress = st.progress(
                    0,
                    text="Préparation...",
                )

                total_photos = len(
                    photos
                )

                for index, photo in enumerate(
                    photos
                ):

                    progress.progress(
                        int(
                            (
                                index
                                / total_photos
                            )
                            * 100
                        ),
                        text=(
                            f"Analyse photo "
                            f"{index + 1}/"
                            f"{total_photos}"
                        ),
                    )

                    img = (
                        Image.open(
                            photo["full_path"]
                        )
                        .convert("RGB")
                    )

                    result = analyser(
                        model_p,
                        model_d,
                        np.array(img),
                        conf_pieces,
                        conf_dommages,
                        iou_min,
                        meta.get(
                            "marque",
                            "",
                        ),
                        photo["filename"],
                        model_z,
                        conf_critical,
                        critical_threshold,
                    )

                    all_results.append(
                        result
                    )

                progress.progress(
                    100,
                    text="Analyse terminée.",
                )

                # ====================================================
                # INSTANCES BRUTES
                # ====================================================

                raw_instances = [
                    item
                    for result in all_results
                    for item in result[
                        "instances"
                    ]
                ]

                # ====================================================
                # DÉDUPLICATION
                # ====================================================

                if dedup:

                    final_instances = (
                        dedupliquer_instances(
                            raw_instances
                        )
                    )

                else:

                    final_instances = (
                        raw_instances
                    )

                # ====================================================
                # RÉCUPÉRATION FEEDBACK EXISTANT
                # ====================================================

                feedbacks = load_feedback(
                    dossier_id
                )

                if feedbacks:

                    final_instances = (
                        appliquer_feedback_aux_instances(
                            final_instances,
                            feedbacks,
                        )
                    )

                # ====================================================
                # RÈGLES REMPLACEMENT
                # ====================================================

                final_instances = (
                    appliquer_priorite_remplacement(
                        final_instances
                    )
                )

                # ====================================================
                # AGRÉGATS
                # ====================================================

                aggregates = (
                    calculer_agregats(
                        final_instances
                    )
                )

                elapsed = (
                    time.time()
                    - start_time
                )

                # ====================================================
                # SESSION
                # ====================================================

                st.session_state.analysis = {

                    "results":
                        all_results,

                    "instances":
                        final_instances,

                    "ag":
                        aggregates,

                    "dossier_id":
                        dossier_id,

                    "elapsed":
                        elapsed,
                }

                set_status(
                    dossier_id,
                    "À valider",
                )

                st.success(
                    f"Analyse terminée en "
                    f"{elapsed:.1f} secondes."
                )

                st.rerun()

            except Exception as e:

                set_status(
                    dossier_id,
                    "Brouillon",
                )

                st.error(
                    f"Impossible de lancer "
                    f"l'analyse : {e}"
                )

    # ========================================================
    # RÉSULTATS
    # ========================================================

    if not has_analysis:

        empty_state(
            "🤖",
            "Aucune analyse disponible",
            "Clique sur « Lancer / relancer l'analyse IA ».",
        )

    else:

        analysis = (
            st.session_state.analysis
        )

        instances = analysis[
            "instances"
        ]

        ag = analysis[
            "ag"
        ]

        pending = pending_count(
            instances
        )

        st.divider()

        section_header(
            "Résumé de l'analyse",
            "Résultats après fusion et règles métier.",
        )

        k1, k2, k3, k4, k5 = st.columns(
            5
        )

        render_kpi(
            k1,
            "🧩",
            "Détections",
            len(instances),
            "Après fusion multi-vues",
        )

        render_kpi(
            k2,
            "✅",
            "Acceptées",
            sum(
                1
                for item in instances
                if detection_acceptee(item)
            ),
            "Validées par l'expert",
            "green",
        )

        render_kpi(
            k3,
            "❌",
            "Rejetées",
            sum(
                1
                for item in instances
                if detection_rejetee(item)
            ),
            "Exclues du chiffrage",
            "red",
        )

        render_kpi(
            k4,
            "⏳",
            "À valider",
            pending,
            "Validation expert",
            "orange",
        )

        render_kpi(
            k5,
            "💰",
            "Total",
            f"{ag['cout_total']:,.0f} MAD",
            "Chiffrage actuel",
            "dark",
        )

        # ====================================================
        # STATISTIQUES FEEDBACK
        # ====================================================

        feedback_stats = (
            statistiques_feedback(
                instances
            )
        )

        st.markdown(
            html(
                f"""
                <div class="info-banner">

                    <b>Contrôle expert</b><br>

                    Total :
                    <b>{feedback_stats['total']}</b>
                    ·

                    Acceptées :
                    <b>{feedback_stats['acceptees']}</b>
                    ·

                    Rejetées :
                    <b>{feedback_stats['rejetees']}</b>
                    ·

                    À valider :
                    <b>{feedback_stats['a_valider']}</b>

                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        # ====================================================
        # DOMMAGES
        # ====================================================

        section_header(
            "Dommages détectés",
            "Chaque détection doit être contrôlée par le chiffreur.",
        )

        if not instances:

            empty_state(
                "✅",
                "Aucun dommage retenu",
                "Aucun dommage n'a été détecté.",
            )

        else:

            severity_colors = {
                "low": "#28a745",
                "mid": "#ffc107",
                "high": "#dc3545",
            }

            for index, item in enumerate(
                sorted(
                    instances,
                    key=lambda x: x.get(
                        "score",
                        0,
                    ),
                    reverse=True,
                )
            ):

                niveau = item.get(
                    "niveau",
                    "mid",
                )

                sev_color = (
                    severity_colors.get(
                        niveau,
                        "#6c757d",
                    )
                )

                sev_label = (
                    LABEL_GRAVITE.get(
                        niveau,
                        str(niveau).capitalize(),
                    )
                )

                detection_id = item.get(
                    "detection_id"
                )

                if not detection_id:
                    detection_id = (
                        f"temp_{index}"
                    )

                # Identifiant unique pour les widgets Streamlit.
                # Une même detection_id peut apparaître plusieurs fois
                # dans l'affichage (multi-vues / doublons non fusionnés).
                widget_id = f"{detection_id}_{index}"

                validation = item.get(
                    "validation_expert",
                    "a_valider",
                )

                # ==================================================
                # COÛT
                # ==================================================

                if detection_rejetee(item):

                    cost = (
                        "❌ Détection rejetée"
                    )

                    cost_color = (
                        "#dc3545"
                    )

                elif item.get(
                    "chiffrage_bloque"
                ):

                    cost = (
                        "Inclus dans remplacement"
                    )

                    cost_color = (
                        "#6c757d"
                    )

                elif item.get(
                    "cout"
                ) is not None:

                    cost = (
                        f"{item['cout']:,.0f} MAD"
                    )

                    cost_color = (
                        "#198754"
                    )

                elif (
                    item.get(
                        "remplacement_requis"
                    )
                    and item.get(
                        "cout_mot"
                    ) is not None
                ):

                    cost = (
                        f"MOT : "
                        f"{item['cout_mot']:,.0f} MAD"
                    )

                    cost_color = (
                        "#fd7e14"
                    )

                elif item.get(
                    "remplacement_requis"
                ):

                    cost = (
                        "Remplacement — "
                        "prix pièce manquant"
                    )

                    cost_color = (
                        "#dc3545"
                    )

                else:

                    cost = (
                        "À vérifier"
                    )

                    cost_color = (
                        "#fd7e14"
                    )

                # ==================================================
                # ZONE CRITIQUE
                # ==================================================

                critical_html = ""

                if item.get(
                    "zone_critique_detectee"
                ):

                    overlap = item.get(
                        "zone_critique_overlap_pct",
                        0,
                    )

                    critical_html = f"""
                        <div style="
                            margin-top:8px;
                            padding:7px 10px;
                            background:#fff3cd;
                            color:#856404;
                            border-radius:7px;
                            font-size:10px;
                        ">
                            🎯 Zone critique
                            · chevauchement {overlap:.0f}%
                            · remplacement
                        </div>
                    """

                # ==================================================
                # CARTE DOMMAGE
                # ==================================================

                border_color = sev_color

                if detection_rejetee(item):

                    border_color = (
                        "#dc3545"
                    )

                elif detection_acceptee(item):

                    border_color = (
                        "#16b879"
                    )

                st.markdown(
                    html(
                        f"""
                        <div
                            class="damage-card"
                            style="
                                border-left:
                                4px solid
                                {border_color};
                            "
                        >

                            <div style="
                                display:flex;
                                justify-content:
                                space-between;
                                gap:15px;
                                flex-wrap:wrap;
                            ">

                                <div style="
                                    flex:1;
                                    min-width:250px;
                                ">

                                    <div class="damage-title">

                                        {item.get(
                                            'type',
                                            '—'
                                        )}

                                        <span style="
                                            color:#6c757d;
                                            font-weight:400;
                                        ">
                                            —
                                            {item.get(
                                                'piece',
                                                '—'
                                            )}
                                        </span>

                                    </div>

                                    <div class="damage-meta">

                                        Confiance :
                                        <b>
                                            {
                                                item.get(
                                                    'confiance',
                                                    0
                                                ) * 100
                                            :.0f}%
                                        </b>

                                        · Surface :
                                        <b>
                                            {
                                                item.get(
                                                    'surface_pct',
                                                    0
                                                )
                                            :.1f}%
                                        </b>

                                        · Vues :
                                        <b>
                                            {
                                                item.get(
                                                    'n_vues',
                                                    1
                                                )
                                            }
                                        </b>

                                    </div>

                                    {critical_html}

                                </div>

                                <div style="
                                    text-align:right;
                                    min-width:170px;
                                ">

                                    <span
                                        class="sev-pill"
                                        style="
                                            background:
                                            {sev_color}15;
                                            color:
                                            {sev_color};
                                        "
                                    >
                                        {sev_label}
                                    </span>

                                    <div style="
                                        margin-top:9px;
                                        font-size:16px;
                                        font-weight:850;
                                        color:
                                        {cost_color};
                                    ">
                                        {cost}
                                    </div>

                                </div>

                            </div>

                        </div>
                        """
                    ),
                    unsafe_allow_html=True,
                )

                # ==================================================
                # STATUT VALIDATION
                # ==================================================

                if detection_a_valider(
                    item
                ):

                    st.markdown(
                        html(
                            """
                            <div class="feedback-pending">
                                ⏳
                                <b>Validation expert requise</b>
                                <br>
                                Cette détection n'est pas encore validée.
                                Elle reste provisoirement incluse dans le
                                chiffrage mais bloque la validation finale.
                            </div>
                            """
                        ),
                        unsafe_allow_html=True,
                    )

                    button_col1, button_col2 = (
                        st.columns(2)
                    )

                    with button_col1:

                        if st.button(
                            "✅ Détection correcte",
                            key=(
                                f"accept_{widget_id}"
                            ),
                            use_container_width=True,
                        ):

                            feedback = (
                                construire_feedback(
                                    dossier_id,
                                    item,
                                    "acceptee",
                                )
                            )

                            upsert_feedback_local(
                                dossier_id,
                                feedback,
                            )

                            appliquer_validation_acceptee(
                                item
                            )

                            recalculer_analysis()

                            st.success(
                                "Détection acceptée."
                            )

                            st.rerun()

                    with button_col2:

                        reject_key = (
                            f"reject_mode_{widget_id}"
                        )

                        if st.button(
                            "❌ Détection incorrecte",
                            key=(
                                f"reject_{widget_id}"
                            ),
                            use_container_width=True,
                        ):

                            st.session_state[
                                reject_key
                            ] = True

                            st.rerun()

                    # ==================================================
                    # FORMULAIRE REJET
                    # ==================================================

                    if st.session_state.get(
                        f"reject_mode_{widget_id}",
                        False,
                    ):

                        st.markdown(
                            "### ❌ Pourquoi cette détection est incorrecte ?"
                        )

                        raison = st.selectbox(
                            "Raison du rejet",
                            [
                                "Mauvaise pièce",
                                "Mauvais dommage",
                                "Fausse détection",
                                "Doublon",
                                "Zone incorrecte",
                                "Gravité incorrecte",
                                "Autre",
                            ],
                            key=(
                                f"raison_{widget_id}"
                            ),
                        )

                        observation = st.text_area(
                            "Observation du chiffreur",
                            placeholder=(
                                "Exemple : "
                                "ce n'est pas une bosse mais une "
                                "trace sur le pare-chocs..."
                            ),
                            key=(
                                f"observation_{widget_id}"
                            ),
                        )

                        correction_piece = st.text_input(
                            "Pièce corrigée (optionnel)",
                            value="",
                            placeholder=(
                                "Exemple : pare-chocs avant"
                            ),
                            key=(
                                f"piece_corrigee_{widget_id}"
                            ),
                        )

                        correction_dommage = st.text_input(
                            "Dommage corrigé (optionnel)",
                            value="",
                            placeholder=(
                                "Exemple : fissure"
                            ),
                            key=(
                                f"dommage_corrige_{widget_id}"
                            ),
                        )

                        save_col1, save_col2 = (
                            st.columns(2)
                        )

                        with save_col1:

                            if st.button(
                                "💾 Enregistrer le rejet",
                                type="primary",
                                key=(
                                    f"save_reject_{widget_id}"
                                ),
                                use_container_width=True,
                            ):

                                feedback = (
                                    construire_feedback(
                                        dossier_id,
                                        item,
                                        "rejetee",
                                        raison,
                                        observation,
                                        correction_piece,
                                        correction_dommage,
                                    )
                                )

                                upsert_feedback_local(
                                    dossier_id,
                                    feedback,
                                )

                                appliquer_validation_rejetee(
                                    item
                                )

                                recalculer_analysis()

                                st.session_state.pop(
                                    f"reject_mode_{widget_id}",
                                    None,
                                )

                                st.success(
                                    "Détection rejetée et exclue du chiffrage."
                                )

                                st.rerun()

                        with save_col2:

                            if st.button(
                                "Annuler",
                                key=(
                                    f"cancel_reject_{widget_id}"
                                ),
                                use_container_width=True,
                            ):

                                st.session_state.pop(
                                    f"reject_mode_{widget_id}",
                                    None,
                                )

                                st.rerun()

                elif detection_acceptee(
                    item
                ):

                    st.markdown(
                        html(
                            """
                            <div class="feedback-ok">
                                ✅
                                <b>Détection validée par l'expert.</b>
                                <br>
                                Cette détection peut participer au chiffrage.
                            </div>
                            """
                        ),
                        unsafe_allow_html=True,
                    )

                elif detection_rejetee(
                    item
                ):

                    raison = item.get(
                        "feedback_raison",
                        "",
                    )

                    observation = item.get(
                        "feedback_observation",
                        "",
                    )

                    st.markdown(
                        html(
                            f"""
                            <div class="feedback-rejected">

                                ❌
                                <b>Détection rejetée.</b>

                                <br>

                                <b>Raison :</b>
                                {raison or "Non renseignée"}

                                <br>

                                <b>Observation :</b>
                                {observation or "Aucune"}

                                <br><br>

                                Cette détection est conservée dans
                                le feedback mais n'est pas comptée
                                dans le chiffrage.

                            </div>
                            """
                        ),
                        unsafe_allow_html=True,
                    )


# ============================================================
# ONGLET 3 — CHIFFRAGE
# ============================================================

with tab_chiffrage:

    section_header(
        "Chiffrage",
        "Réparation, remplacement et prix des pièces.",
    )

    if not has_analysis:

        empty_state(
            "💰",
            "Chiffrage indisponible",
            "Lance d'abord l'analyse IA.",
        )

    else:

        analysis = (
            st.session_state.analysis
        )

        instances = analysis[
            "instances"
        ]

        ag = analysis[
            "ag"
        ]

        pending = pending_count(
            instances
        )

        # ====================================================
        # AVERTISSEMENT VALIDATION
        # ====================================================

        if pending > 0:

            st.warning(
                f"⚠️ {pending} détection(s) "
                "doivent encore être validée(s) par l'expert."
            )

        st.markdown(
            html(
                """
                <div class="info-banner">

                    <b>Principe du chiffrage</b><br>

                    • Une détection rejetée n'est jamais incluse
                    dans le chiffrage.<br>

                    • Une détection acceptée peut être chiffrée.<br>

                    • Les remplacements nécessitent un prix pièce.<br>

                    • Les prix pièces proviennent d'AutoEstimate.<br>

                    • L'expert conserve la validation finale.

                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        # ====================================================
        # PIÈCES À REMPLACER
        # ====================================================

        replacement_items = [
            item
            for item in instances
            if item.get(
                "remplacement_requis"
            )
            and not detection_rejetee(
                item
            )
        ]

        if replacement_items:

            section_header(
                "1 · Pièces à remplacer",
                "Choisis le type de pièce avant de récupérer le prix.",
            )

            type_choices = st.session_state.setdefault(
                "type_choices",
                {},
            )

            for item in replacement_items:

                key = item_key(
                    item
                )

                default_type = (
                    item.get(
                        "type_piece"
                    )
                    or "occasion"
                )

                if (
                    default_type
                    not in TYPES_PIECE_API
                ):

                    default_type = (
                        "occasion"
                    )

                st.markdown(
                    f"**🔩 {item.get('piece', 'Pièce')}**"
                )

                chosen = st.selectbox(
                    "Type de pièce",
                    TYPES_PIECE_API,
                    index=TYPES_PIECE_API.index(
                        default_type
                    ),
                    format_func=lambda x: {
                        "original":
                            "🟦 Original",
                        "adaptable":
                            "🟨 Adaptable",
                        "occasion":
                            "🟩 Occasion",
                    }.get(
                        x,
                        x,
                    ),
                    key=(
                        f"type_piece_"
                        f"{key}"
                    ),
                )

                type_choices[
                    key
                ] = chosen

                st.divider()

            # =================================================
            # AUTOESTIMATE
            # =================================================

            if st.button(
                "🔄 Récupérer les prix AutoEstimate",
                type="primary",
                use_container_width=True,
            ):

                marque_id = meta.get(
                    "marque_id"
                )

                model_id = meta.get(
                    "model_id"
                )

                year_value = meta.get(
                    "annee"
                )

                year = (
                    int(year_value)
                    if str(
                        year_value
                    ).isdigit()
                    else None
                )

                if not marque_id:

                    st.error(
                        "Le dossier ne contient "
                        "pas de marque_id AutoEstimate."
                    )

                elif not model_id:

                    st.error(
                        "Le dossier ne contient "
                        "pas de model_id AutoEstimate."
                    )

                else:

                    try:

                        with st.spinner(
                            "Recherche des prix pièces..."
                        ):

                            enrichir_prix_pieces(
                                instances,
                                marque_id,
                                model_id,
                                year,
                                type_choices,
                            )

                            st.session_state.analysis[
                                "instances"
                            ] = instances

                            st.session_state.analysis[
                                "ag"
                            ] = (
                                calculer_agregats(
                                    instances
                                )
                            )

                        st.success(
                            "Les prix AutoEstimate "
                            "ont été mis à jour."
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(
                            f"Erreur AutoEstimate : {e}"
                        )

        else:

            st.success(
                "Aucun remplacement à chiffrer."
            )

        # ====================================================
        # TOTAL
        # ====================================================

        ag = st.session_state.analysis[
            "ag"
        ]

        section_header(
            "2 · Synthèse financière",
            "Vue globale du chiffrage.",
        )

        st.markdown(
            html(
                f"""
                <div class="price-card">

                    <div class="price-title">
                        💰 Total estimé du dossier
                    </div>

                    <div class="price-value">
                        {ag['cout_total']:,.0f} MAD
                    </div>

                    <div class="price-meta">
                        Les détections rejetées sont exclues.
                    </div>

                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        # ====================================================
        # KPI
        # ====================================================

        a, b, c, d, e = st.columns(5)

        render_kpi(
            a,
            "🔧",
            "MO Tôlerie",
            f"{ag['total_mo_reparation']:,.0f} MAD",
            "Réparation C2",
        )

        render_kpi(
            b,
            "🎨",
            "MOP",
            f"{ag['total_mo_peinture']:,.0f} MAD",
            "Peinture",
            "dark",
        )

        render_kpi(
            c,
            "🧴",
            "MET",
            f"{ag['total_produit_peinture']:,.0f} MAD",
            "Produits peinture",
        )

        render_kpi(
            d,
            "🔩",
            "MOT",
            f"{ag.get('total_mot', 0):,.0f} MAD",
            "Échange",
            "dark",
        )

        render_kpi(
            e,
            "📦",
            "Pièces",
            f"{ag['total_fourniture']:,.0f} MAD",
            "Fourniture",
            "orange",
        )

        # ====================================================
        # TABLEAU
        # ====================================================

        section_header(
            "3 · Détail du chiffrage",
            "Vue ligne par ligne.",
        )

        rows = []

        for item in sorted(
            instances,
            key=lambda x: x.get(
                "score",
                0,
            ),
            reverse=True,
        ):

            # REJETÉ
            if detection_rejetee(
                item
            ):

                cost = (
                    "Exclu — rejet expert"
                )

                action = "Exclu"

            elif item.get(
                "chiffrage_bloque"
            ):

                cost = (
                    "Inclus remplacement"
                )

                action = "Remplacement"

            elif item.get(
                "cout"
            ) is not None:

                cost = (
                    f"{item['cout']:,.0f} MAD"
                )

                action = (
                    "Remplacement"
                    if item.get(
                        "remplacement_requis"
                    )
                    else "Réparation"
                )

            elif (
                item.get(
                    "remplacement_requis"
                )
                and item.get(
                    "cout_mot"
                ) is not None
            ):

                cost = (
                    f"MOT "
                    f"{item['cout_mot']:,.0f} MAD "
                    f"+ pièce"
                )

                action = "Remplacement"

            else:

                cost = (
                    "À vérifier"
                )

                action = (
                    "Remplacement"
                    if item.get(
                        "remplacement_requis"
                    )
                    else "Réparation"
                )

            rows.append(
                {
                    "Dommage":
                        item.get(
                            "type",
                            "—",
                        ),

                    "Pièce":
                        item.get(
                            "piece",
                            "—",
                        ),

                    "Gravité":
                        LABEL_GRAVITE.get(
                            item.get(
                                "niveau"
                            ),
                            "—",
                        ),

                    "Validation":
                        (
                            "❌ Rejetée"
                            if detection_rejetee(
                                item
                            )
                            else
                            "✅ Acceptée"
                            if detection_acceptee(
                                item
                            )
                            else
                            "⏳ À valider"
                        ),

                    "Action":
                        action,

                    "Coût":
                        cost,
                }
            )

        if rows:

            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True,
            )

        if pending > 0:

            st.warning(
                f"{pending} ligne(s) "
                "nécessitent encore une validation experte."
            )


# ============================================================
# ONGLET 4 — CONTRÔLE VISUEL
# ============================================================

with tab_controle:

    section_header(
        "Contrôle visuel",
        "Comparer les images originales avec les résultats IA.",
    )

    if not has_analysis:

        empty_state(
            "🖼️",
            "Aucune visualisation disponible",
            "Lance d'abord l'analyse IA.",
        )

    else:

        analysis = (
            st.session_state.analysis
        )

        for result in analysis[
            "results"
        ]:

            image_name = result.get(
                "nom",
                "Photo",
            )

            st.markdown(
                f"### 📸 {image_name}"
            )

            blocks = [
                (
                    "Pièces détectées",
                    result[
                        "img_pieces"
                    ],
                    "#18212B",
                ),

                (
                    "Dommages détectés",
                    result[
                        "img_dommages"
                    ],
                    "#18212B",
                ),
            ]

            if result.get(
                "img_zones_critiques"
            ) is not None:

                blocks.append(
                    (
                        "Zone critique",
                        result[
                            "img_zones_critiques"
                        ],
                        "#dc3545",
                    )
                )

            columns = st.columns(
                len(blocks)
            )

            for col, (
                title,
                array,
                color,
            ) in zip(
                columns,
                blocks,
            ):

                with col:

                    st.markdown(
                        f"""
                        <div
                            class="viz-col-title"
                            style="color:{color};"
                        >
                            {title}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    st.markdown(
                        html(
                            f"""
                            <img
                                src="{array_to_data_uri(array)}"
                                class="viz-img"
                                alt="{title}"
                            />
                            """
                        ),
                        unsafe_allow_html=True,
                    )

            st.divider()


# ============================================================
# PDF
# ============================================================

def _pdf_money(value, dash_if_zero=False):
    """Format monétaire CABEK : 1 500,00."""
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0.0
    if dash_if_zero and abs(value) < 1e-9:
        return "----"
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")


def _pdf_text(value, default="----"):
    if value is None or str(value).strip() == "":
        return default
    return str(value)


def _pdf_date(value):
    if not value:
        return "----"
    return str(value)[:10]


def _pdf_num_to_words_fr(n):
    """Conversion simple des montants en lettres, suffisante pour le rapport DH."""
    units = [
        "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept",
        "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
    ]

    def under_100(x):
        if x < 17:
            return units[x]
        if x < 20:
            return "dix-" + units[x - 10]
        tens = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}
        if x < 70:
            t = (x // 10) * 10
            r = x % 10
            return tens[t] if r == 0 else tens[t] + ("-et-un" if r == 1 else "-" + units[r])
        if x < 80:
            r = x - 60
            return "soixante-dix" if r == 10 else "soixante-" + under_100(r)
        r = x - 80
        return "quatre-vingts" if r == 0 else "quatre-vingt-" + under_100(r)

    def under_1000(x):
        if x < 100:
            return under_100(x)
        h, r = divmod(x, 100)
        base = "cent" if h == 1 else units[h] + " cent"
        if r == 0 and h > 1:
            base += "s"
        return base if r == 0 else base + " " + under_100(r)

    try:
        n = int(round(float(n)))
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        return "moins " + _pdf_num_to_words_fr(-n)
    if n < 1000:
        return under_1000(n)
    if n < 1_000_000:
        q, r = divmod(n, 1000)
        base = "mille" if q == 1 else under_1000(q) + " mille"
        return base if r == 0 else base + " " + under_1000(r)
    return str(n)


def generate_pdf(meta, instances, ag):
    """Génère le rapport CABEK au format métier de référence (2 pages A4)."""

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=9 * mm,
        leftMargin=9 * mm,
        topMargin=25 * mm,
        bottomMargin=17 * mm,
        title="Rapport d'expertise CABEK",
        author="CABEK",
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "CabekPdfNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=8.5,
        textColor=colors.HexColor("#202020"),
    )
    small = ParagraphStyle(
        "CabekPdfSmall",
        parent=normal,
        fontSize=6.2,
        leading=7.2,
    )
    header_style = ParagraphStyle(
        "CabekPdfHeader",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        "CabekPdfSection",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=10,
        spaceBefore=1,
        spaceAfter=1,
    )

    DARK = colors.HexColor("#222222")
    BORDER = colors.HexColor("#777777")
    LIGHT = colors.HexColor("#F2F2F2")
    WHITE = colors.white

    # -----------------------------------------------------------------
    # EN-TÊTE / PIED DE PAGE — repris du document CABEK de référence.
    # -----------------------------------------------------------------
    def header_footer(canvas, doc):
        canvas.saveState()
        width, height = A4
        x0, x1 = 9 * mm, width - 9 * mm

        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(DARK)
        canvas.drawCentredString(width / 2, height - 10 * mm, "CABINET D’EXPERTISE KHAMLICHI")
        canvas.setFont("Helvetica", 6.5)
        canvas.drawCentredString(width / 2, height - 14 * mm, "Expert assermenté près les tribunaux du MAROC")
        canvas.drawCentredString(width / 2, height - 17.5 * mm,
                                 "Matériels roulant – Risque divers – Dégât des eaux – Marchandises transportées")
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.35)
        canvas.line(x0, height - 20 * mm, x1, height - 20 * mm)

        canvas.setFont("Helvetica", 6.2)
        canvas.setFillColor(colors.HexColor("#333333"))
        canvas.drawCentredString(
            width / 2, 8.5 * mm,
            "49, Rue Karatchi 2ème étage N°7 / Tél : +212 522-458989 / +212 6 93887718"
        )
        canvas.drawCentredString(
            width / 2, 5.7 * mm,
            "E-mail : cabek.expertise@gmail.com / ICE : 001551053000058 - I.F: 1602830"
        )
        canvas.drawCentredString(
            width / 2, 2.9 * mm,
            "TAXE PROFESSIONNELLE : 37950415 - R.C : 152371 – C.N.S.S: 7270903"
        )
        canvas.restoreState()

    story = []

    # -----------------------------------------------------------------
    # PAGE 1 — RAPPORT D'EXPERTISE
    # -----------------------------------------------------------------
    story.append(Paragraph(
        "RAPPORT D'EXPERTISE (MODE: RAPIDE)",
        ParagraphStyle("ReportTitle", parent=normal, fontName="Helvetica-Bold", fontSize=10.5,
                       leading=12, alignment=TA_CENTER, spaceAfter=2),
    ))

    ref = _pdf_text(meta.get("reference") or meta.get("ref") or meta.get("dossier_id"))
    date_ouverture = _pdf_date(meta.get("date_ouverture") or meta.get("created_at"))
    date_sinistre = _pdf_date(meta.get("date_sinistre"))
    expert = _pdf_text(meta.get("expert"), "Cabek")
    compte = _pdf_text(meta.get("pour_le_compte") or meta.get("compagnie"), "----")
    sinistre = _pdf_text(meta.get("sinistre") or meta.get("sinistre_nom") or meta.get("nom_assure"))
    intermediaire = _pdf_text(meta.get("intermediaire"))
    police = _pdf_text(meta.get("numero_police") or meta.get("police"))
    garantie = _pdf_text(meta.get("garantie") or meta.get("mode"), "RAPIDE")
    matricule = _pdf_text(meta.get("matricule"))
    adverse = _pdf_text(meta.get("sinistre_adverse") or meta.get("sinistre_adverse_nom"))

    info_rows = [
        ["Ref :", ref, "Date d’ouverture", date_ouverture],
        ["Date du sinistre", date_sinistre, "Par l’Expert", expert],
        ["Pour le compte de", compte, "Le sinistré", sinistre],
        ["Par l’intermédiaire de", intermediaire, "N° de police", police],
        ["Garantie affectée", garantie, "Matricule", matricule],
        ["Le sinistré adverse", adverse, "", ""],
        ["Assuré par N° de police", _pdf_text(meta.get("police_adverse")), "Propriétaire d’une", _pdf_text(meta.get("proprietaire"))],
        ["Matricule adverse", _pdf_text(meta.get("matricule_adverse")), "", ""],
    ]
    info = Table(info_rows, colWidths=[38*mm, 48*mm, 38*mm, 52*mm], hAlign="LEFT")
    info.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, BORDER),
        ("BACKGROUND", (0,0), (0,-1), LIGHT),
        ("BACKGROUND", (2,0), (2,-1), LIGHT),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 6.6),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 1.2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1.2),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(info)
    story.append(Spacer(1, 1.0*mm))

    dates_rows = [
        ["Expertise avant réparation le", _pdf_date(meta.get("date_expertise_avant")),
         "Réception du devis des réparations le", _pdf_date(meta.get("date_devis_recu"))],
        ["Devis des réparations accordé le", _pdf_date(meta.get("date_devis_accorde")),
         "Expertise en cours de réparation le", _pdf_date(meta.get("date_en_cours_reparation"))],
        ["Expertise après réparation le", _pdf_date(meta.get("date_apres_reparation")),
         "Réception de la facture des réparations le", _pdf_date(meta.get("date_facture_recue"))],
        ["Lieu d’expertise", _pdf_text(meta.get("lieu_expertise"), "Autre Garage"),
         "Montant", _pdf_money(ag.get("cout_total", 0), dash_if_zero=True)],
    ]
    dt = Table(dates_rows, colWidths=[48*mm, 40*mm, 52*mm, 36*mm])
    dt.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, BORDER),
        ("BACKGROUND", (0,0), (0,-1), LIGHT),
        ("BACKGROUND", (2,0), (2,-1), LIGHT),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 6.5),
        ("TOPPADDING", (0,0), (-1,-1), 1.2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1.2),
    ]))
    story.append(dt)
    story.append(Spacer(1, 1.0*mm))

    # Véhicule
    story.append(Paragraph("Véhicule expertisé", section_style))
    vehicle_rows = [
        ["Point de choc", _pdf_text(meta.get("point_choc")), "Marque", _pdf_text(meta.get("marque"))],
        ["Model", _pdf_text(meta.get("modele")), "Cylindre", _pdf_text(meta.get("cylindre"))],
        ["N° d'immatriculation", matricule, "Date de M.C.", _pdf_text(meta.get("date_mc") or meta.get("annee"))],
        ["Type Mine", _pdf_text(meta.get("type_mine")), "Couleur /Teinte", _pdf_text(meta.get("couleur"))],
        ["V.I.N", _pdf_text(meta.get("vin")), "Carburant", _pdf_text(meta.get("carburant"))],
        ["Puissance fiscale", _pdf_text(meta.get("puissance_fiscale")), "kilométrage", _pdf_text(meta.get("kilometrage"))],
        ["Dernière V.Technique", _pdf_text(meta.get("derniere_vt")), "Usure des pneus", _pdf_text(meta.get("usure_pneus"))],
        ["Etat général post-sinistre", _pdf_text(meta.get("etat_general"), "Bon"), "", ""],
    ]
    vt = Table(vehicle_rows, colWidths=[40*mm, 50*mm, 40*mm, 46*mm])
    vt.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, BORDER),
        ("BACKGROUND", (0,0), (0,-1), LIGHT),
        ("BACKGROUND", (2,0), (2,-1), LIGHT),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 6.6),
        ("TOPPADDING", (0,0), (-1,-1), 1.2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1.2),
    ]))
    story.append(vt)
    story.append(Spacer(1, 1.0*mm))

    # Évaluation chiffrée
    story.append(Paragraph(
        "Evaluation chiffrée des dommages (Si appliqué, le taux de TVA est 20%)",
        section_style,
    ))
    total_rep = float(ag.get("total_mo_reparation", 0) or 0)
    total_peinture = float(ag.get("total_mo_peinture", 0) or 0)
    total_mot = float(ag.get("total_mot", 0) or 0)
    total_produit = float(ag.get("total_produit_peinture", 0) or 0)
    detail_fourniture = calculer_detail_fourniture(instances)
    total_fourniture = float(detail_fourniture.get("total_fourniture", ag.get("total_fourniture", 0)) or 0)

    mo_rows = [["Main d'oeuvre", "Taux horaires(Dhs/h)", "Temps imparti(h)", "Total H.T", "Total TVA", "Total T.T.C"]]
    mo_rows += [
        ["Dressage", "F", "F", _pdf_money(total_rep), _pdf_money(0), _pdf_money(total_rep)],
        ["Changement", "F", "F", _pdf_money(total_mot), _pdf_money(0), _pdf_money(total_mot)],
        ["Mecanique", "0", "0", _pdf_money(0), _pdf_money(0), _pdf_money(0)],
        ["Peinture", "F", "F", _pdf_money(total_peinture), _pdf_money(0), _pdf_money(total_peinture)],
        ["Electrique", "0", "0", _pdf_money(0), _pdf_money(0), _pdf_money(0)],
        ["Pare Brise", "0", "0", _pdf_money(0), _pdf_money(0), _pdf_money(0)],
    ]
    total_mo = total_rep + total_mot + total_peinture
    mo_rows += [["Conclusion: Total M.O", "", "", _pdf_money(total_mo), _pdf_money(0), _pdf_money(total_mo)]]
    mo_rows += [["Total Fournitures", "", "", _pdf_money(total_fourniture), _pdf_money(0), _pdf_money(total_fourniture)]]
    mo_rows += [["Montant des dommages", "", "", _pdf_money(total_mo + total_fourniture), _pdf_money(0), _pdf_money(total_mo + total_fourniture)]]

    mot = Table(mo_rows, colWidths=[43*mm, 31*mm, 28*mm, 27*mm, 27*mm, 27*mm], repeatRows=1)
    mot.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), LIGHT),
        ("GRID", (0,0), (-1,-1), 0.3, BORDER),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME", (0,-3), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 6.4),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("TOPPADDING", (0,0), (-1,-1), 1),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1),
    ]))
    story.append(mot)
    story.append(Spacer(1, 1.0*mm))

    # Indemnisation
    montant_dommages = total_mo + total_fourniture
    plafond = meta.get("plafond")
    vetuste = float(meta.get("vetuste", 0) or 0)
    remise = float(meta.get("remise", 0) or 0)
    tva = float(meta.get("tva", 0) or 0)
    franchise = float(meta.get("franchise", 0) or 0)
    indemnisation = float(meta.get("montant_indemnisation", montant_dommages - vetuste - remise - tva - franchise) or 0)

    indemn_rows = [
        ["", "Total H.T", "Total T.T.C"],
        ["Plafond", _pdf_text(plafond, "----"), _pdf_money(0)],
        ["-Vétusté", _pdf_money(vetuste), "----"],
        ["-Remise", _pdf_money(remise), "----"],
        ["-T.V.A (20%)", _pdf_money(tva), "----"],
        ["Franchise", _pdf_money(franchise), "----"],
        ["Montatnt d'indemnisation", _pdf_money(indemnisation), _pdf_money(indemnisation)],
    ]
    ind = Table(indemn_rows, colWidths=[82*mm, 52*mm, 49*mm])
    ind.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), LIGHT),
        ("GRID", (0,0), (-1,-1), 0.3, BORDER),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 6.5),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("TOPPADDING", (0,0), (-1,-1), 1.2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1.2),
    ]))
    story.append(ind)
    story.append(Spacer(1, 1.0*mm))

    story.append(Paragraph("LE PRESENT RAPPORT EST ARRÊTE A LA SOMME DE :", normal))
    story.append(Paragraph(f"En chiffre <b>{_pdf_money(indemnisation)} DH</b>", normal))
    story.append(Paragraph(f"En lettre <b>{_pdf_num_to_words_fr(indemnisation)} dirhams</b>", normal))
    story.append(Spacer(1, 0.8*mm))
    story.append(Paragraph(
        "En foi de quoi, nous avons dressé et clos le présent rapport d'expertise pour servir et valoir ce que de droit",
        normal,
    ))
    story.append(Spacer(1, 1.0*mm))
    story.append(Paragraph(
        f"M.M'hamed Khamlichi Cabek, {_pdf_date(meta.get('date_rapport') or meta.get('date_expertise_avant') or datetime.now().date().isoformat())}",
        normal,
    ))

    # -----------------------------------------------------------------
    # PAGE 2 — DÉTAILS FOURNITURES & PEINTURE
    # -----------------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph(
        "Détails fournitures & ingrédients peinture (Si appliqué, le taux de TVA est 20%)",
        ParagraphStyle("DetailTitle", parent=normal, fontName="Helvetica-Bold", fontSize=8.5,
                       leading=10, spaceAfter=2),
    ))

    detail_rows = [[
        "Désignation", "Qté", "Opération", "Type pièce", "P.U H.T", "TVA U", "P.U T.T.C",
        "Vetusté %", "Remise %", "T.T.C"
    ]]

    # Le rapport final ne reprend que les détections non rejetées.
    for item in instances:
        if detection_rejetee(item) or item.get("chiffrage_bloque"):
            continue

        piece = _pdf_text(item.get("piece"), "Pièce")
        operation = "ECHANGE" if item.get("remplacement_requis") else "REPARATION"
        type_piece = _pdf_text(item.get("type_piece"))
        prix_piece = item.get("prix_piece")
        if operation == "ECHANGE" and prix_piece is None:
            prix_piece = item.get("cout_mot")

        if operation == "ECHANGE":
            pu = float(prix_piece or 0)
        else:
            pu = 0.0

        detail_rows.append([
            piece.upper(),
            "1",
            operation,
            type_piece.upper(),
            _pdf_money(pu),
            _pdf_money(0),
            _pdf_money(pu),
            "--",
            "--",
            _pdf_money(pu),
        ])

    if total_produit > 0:
        detail_rows.append([
            "Peinture et ingredients", "1", "ECHANGE", "--",
            _pdf_money(total_produit), _pdf_money(0), _pdf_money(total_produit),
            "--", "--", _pdf_money(total_produit),
        ])

    if len(detail_rows) == 1:
        detail_rows.append([
            "Aucune fourniture enregistrée", "", "", "", _pdf_money(0), _pdf_money(0),
            _pdf_money(0), "--", "--", _pdf_money(0),
        ])

    detail = Table(
        detail_rows,
        colWidths=[35*mm, 9*mm, 24*mm, 24*mm, 17*mm, 15*mm, 19*mm, 15*mm, 15*mm, 19*mm],
        repeatRows=1,
    )
    detail.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), LIGHT),
        ("GRID", (0,0), (-1,-1), 0.3, BORDER),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 5.8),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 1),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1),
        ("LEFTPADDING", (0,0), (-1,-1), 2),
        ("RIGHTPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(detail)

    document.build(
        story,
        onFirstPage=header_footer,
        onLaterPages=header_footer,
    )

    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# ONGLET 5 — VALIDATION & RAPPORT
# ============================================================

with tab_rapport:

    section_header(
        "Validation finale",
        "Dernière étape avant transmission du dossier.",
    )

    if not has_analysis:

        empty_state(
            "📄",
            "Rapport non disponible",
            "Lance d'abord l'analyse IA.",
        )

    else:

        analysis = (
            st.session_state.analysis
        )

        instances = analysis[
            "instances"
        ]

        ag = analysis[
            "ag"
        ]

        pending = pending_count(
            instances
        )

        # ====================================================
        # ÉTAT VALIDATION
        # ====================================================

        if pending > 0:

            st.markdown(
                html(
                    f"""
                    <div class="validation-card warning">

                        <div class="validation-title">
                            ⏳ Validation experte incomplète
                        </div>

                        <div class="validation-text">
                            {pending}
                            détection(s) doivent encore être
                            acceptées ou rejetées par le chiffreur.
                            <br><br>
                            La validation finale du dossier est bloquée.
                        </div>

                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )

        elif ag.get(
            "n_a_verifier",
            0,
        ) > 0:

            st.markdown(
                html(
                    f"""
                    <div class="validation-card warning">

                        <div class="validation-title">
                            ⚠️ Chiffrage incomplet
                        </div>

                        <div class="validation-text">
                            {ag['n_a_verifier']}
                            ligne(s) nécessitent encore une action
                            de chiffrage, par exemple un prix pièce.
                            <br><br>
                            La validation finale reste bloquée.
                        </div>

                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )

        else:

            st.markdown(
                html(
                    """
                    <div class="validation-card">

                        <div class="validation-title">
                            ✅ Dossier prêt pour validation
                        </div>

                        <div class="validation-text">
                            Toutes les détections ont été contrôlées
                            et le chiffrage ne contient plus d'élément bloquant.
                        </div>

                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )

        # ====================================================
        # RÉSUMÉ
        # ====================================================

        a, b, c, d = st.columns(4)

        render_kpi(
            a,
            "🧩",
            "Dommages",
            len(instances),
            "Détections après fusion",
        )

        render_kpi(
            b,
            "✅",
            "Acceptées",
            sum(
                1
                for item in instances
                if detection_acceptee(
                    item
                )
            ),
            "Validées",
            "green",
        )

        render_kpi(
            c,
            "❌",
            "Rejetées",
            sum(
                1
                for item in instances
                if detection_rejetee(
                    item
                )
            ),
            "Exclues du chiffrage",
            "red",
        )

        render_kpi(
            d,
            "💰",
            "Total",
            f"{ag['cout_total']:,.0f} MAD",
            "Estimation actuelle",
            "dark",
        )

        # ====================================================
        # VALIDATION
        # ====================================================

        section_header(
            "Validation de l'expertise",
            "L'expert garde la décision finale.",
        )

        can_validate = (
            pending == 0
            and ag.get(
                "n_a_verifier",
                0,
            ) == 0
        )

        if not can_validate:

            st.button(
                "🔒 Valider l'expertise",
                type="primary",
                use_container_width=True,
                disabled=True,
                help=(
                    "La validation est bloquée tant qu'il "
                    "reste des détections ou lignes à vérifier."
                ),
            )

            st.info(
                "Pour débloquer la validation : "
                "traite toutes les détections « À valider » "
                "et complète les lignes de chiffrage restantes."
            )

        else:

            if st.button(
                "✅ Valider l'expertise",
                type="primary",
                use_container_width=True,
            ):

                set_status(
                    dossier_id,
                    "Validé",
                )

                st.success(
                    "Expertise validée avec succès."
                )

                st.rerun()

        # ====================================================
        # RAPPORT PDF
        # ====================================================

        st.divider()

        section_header(
            "Rapport PDF",
            "Générer le rapport de l'expertise.",
        )

        pdf = generate_pdf(
            meta,
            instances,
            ag,
        )

        st.download_button(
            "📄 Générer / télécharger le rapport PDF",
            data=pdf,
            file_name=(
                f"rapport_{dossier_id}.pdf"
            ),
            mime="application/pdf",
            use_container_width=True,
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "CABEK.AI · L'IA propose une analyse et un chiffrage "
    "provisoire ; l'expert conserve la validation finale. "
    "Les détections rejetées sont conservées comme feedback "
    "pour l'amélioration future du modèle."
)