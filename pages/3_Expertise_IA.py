import io
import time
import base64
from pathlib import Path

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
)

from core.parts_pricing import TYPES_PIECE_API

from bareme_c2 import (
    TARIF_REPARATION_DH,
    TARIF_MOP_DH,
)

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# ============================================================
# CONFIGURATION
# ============================================================
# st.set_page_config() N'EST PAS appelé ici : dans une app multipage
# (app.py -> pg.run()), il est déjà appelé une seule fois dans app.py.
# L'appeler une deuxième fois dans une sous-page fait planter Streamlit
# avec StreamlitAPIException dès qu'on navigue vers cette page.


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
    Transforme une image locale en Data URI
    afin de l'afficher dans du HTML.
    """
    path = Path(path)

    data = path.read_bytes()

    ext = path.suffix.lower().lstrip(".")

    mime = "jpeg" if ext in ("jpg", "jpeg") else ext

    return (
        f"data:image/{mime};base64,"
        f"{base64.b64encode(data).decode()}"
    )


def array_to_data_uri(arr, fmt="JPEG") -> str:
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
# STATUTS
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
# CSS
# ============================================================

st.markdown(
    html(
        """
        <style>

        /* =====================================================
           GLOBAL
        ===================================================== */

        .block-container {
            max-width: 1450px;
            padding-top: 1.5rem;
            padding-bottom: 4rem;
        }

        /* =====================================================
           HEADER DOSSIER
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

        .workflow-item.active {
            border-color: #1769d5;
            background: #eef6ff;
        }

        .workflow-item.done {
            border-color: #b9e7d3;
            background: #f2fbf7;
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

        .workflow-item.active .workflow-number {
            background: #1769d5;
            color: white;
        }

        .workflow-item.done .workflow-number {
            background: #16b879;
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
           EMPTY STATE
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
           VALIDATION
        ===================================================== */

        .validation-card {
            background: #f2fbf7;
            border: 1px solid #bfe9d6;
            border-radius: 14px;
            padding: 18px;
            margin-bottom: 18px;
        }

        .validation-title {
            font-size: 15px;
            font-weight: 850;
            color: #145c40;
        }

        .validation-text {
            font-size: 11px;
            color: #557466;
            margin-top: 5px;
        }

        /* =====================================================
           VISUALISATIONS IA — taille moyenne, cohérent avec
           le reste de l'app (pas de plein écran)
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
# SIDEBAR — SÉLECTION DU DOSSIER
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

    selected = dossiers[selected_idx]

    st.divider()

    st.markdown("### ⚙️ Paramètres IA")

    with st.expander(
        "Paramètres avancés",
        expanded=False,
    ):

        path_pieces = st.text_input(
            "Modèle pièces",
            "models/best_pieces.pt",
        )

        path_dommages = st.text_input(
            "Modèle dommages",
            "models/best.pt",
        )

        use_critical = st.checkbox(
            "Activer la zone critique",
            value=True,
        )

        path_critical = st.text_input(
            "Modèle zone critique",
            "models/best_zone_critique.pt",
            disabled=not use_critical,
        )

        conf_pieces = st.slider(
            "Confiance pièces",
            0.05,
            0.95,
            0.25,
            0.05,
        )

        conf_dommages = st.slider(
            "Confiance dommages",
            0.05,
            0.95,
            0.15,
            0.05,
        )

        iou_min = st.slider(
            "Association dommage ↔ pièce",
            0.0,
            0.5,
            0.05,
            0.01,
        )

        if use_critical:

            conf_critical = st.slider(
                "Confiance zone critique",
                0.05,
                0.95,
                0.25,
                0.05,
            )

            critical_threshold = st.slider(
                "Seuil intersection zone critique",
                0.0,
                0.5,
                0.05,
                0.01,
            )

        else:

            conf_critical = 0.25
            critical_threshold = 0.05

        dedup = st.checkbox(
            "Fusionner les vues multiples",
            value=True,
        )


# ============================================================
# MÉTADONNÉES
# ============================================================

dossier_id = selected["dossier_id"]

meta = load_metadata(dossier_id)

photos = photo_paths(dossier_id)


# ============================================================
# RESET ANALYSE SI CHANGEMENT DE DOSSIER
# ============================================================

analysis = st.session_state.get("analysis")

if (
    analysis is not None
    and analysis.get("dossier_id") != dossier_id
):

    st.session_state.pop(
        "analysis",
        None,
    )

    analysis = None


has_analysis = (
    analysis is not None
    and analysis.get("dossier_id") == dossier_id
)


# ============================================================
# HEADER DU DOSSIER
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
# WORKFLOW — 5 étapes, alignées sur les 5 onglets ci-dessous
# ============================================================
# "Terminé" reflète un état réellement atteint, pas seulement "possible" :
# - Chiffrage : marqué Terminé seulement quand plus rien n'est "à vérifier",
#   pas seulement quand il y a (ou non) un remplacement à faire.
# - Validation & rapport : marqué Terminé seulement une fois le statut du
#   dossier passé à "Validé".

ag_courant = analysis.get("ag") if has_analysis else None

step1 = len(photos) > 0
step2 = has_analysis
step3 = has_analysis and ag_courant is not None and ag_courant.get("n_a_verifier", 1) == 0
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

    cls = "done" if done else ""

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
# INFORMATIONS RAPIDES
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
#
# 1. Dossier
# 2. Analyse & résultats
# 3. Chiffrage
# 4. Contrôle visuel
# 5. Rapport
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
            "Ajoute les quatre vues principales depuis « Collecte des données ».",
        )

    else:

        st.markdown(
            html(
                """
                <div class="info-banner">
                    <b>Avant de lancer l'analyse :</b>
                    vérifie que les photos avant, arrière, gauche et droite
                    sont présentes et suffisamment visibles.
                    Les photos de détails peuvent compléter l'analyse.
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        # ----------------------------------------------------
        # PHOTO PRINCIPALE
        # ----------------------------------------------------

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

        selected_photo = photos[photo_idx]

        uri = file_to_data_uri(
            selected_photo["full_path"]
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

        # ----------------------------------------------------
        # GALERIE
        # ----------------------------------------------------

        section_header(
            "Toutes les photos",
            f"{len(photos)} photo(s) enregistrée(s) dans le dossier.",
        )

        columns = st.columns(
            min(4, len(photos))
        )

        for index, photo in enumerate(photos):

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
# ONGLET 2 — ANALYSE & RÉSULTATS
# ============================================================

with tab_analyse:

    section_header(
        "Analyse IA",
        "Lance l'analyse complète du dossier en une seule action.",
    )

    st.markdown(
        html(
            """
            <div class="info-banner">

                <b>Pipeline CABEK.AI</b><br>

                ① Détection des pièces
                →
                ② Détection des dommages
                →
                ③ Association dommage / pièce
                →
                ④ Zone critique
                →
                ⑤ Règles métier
                →
                ⑥ Fusion des vues

            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # BOUTON ANALYSE
    # --------------------------------------------------------

    if not photos:

        st.warning(
            "Impossible de lancer l'analyse : "
            "aucune photo n'est disponible."
        )

    else:

        if has_analysis:

            st.success(
                f"Une analyse existe déjà pour ce dossier "
                f"({analysis.get('elapsed', 0):.1f} secondes)."
            )

        launch = st.button(
            "🚀 Lancer / relancer l'analyse IA",
            type="primary",
            use_container_width=True,
        )

        if launch:

            try:

                # ------------------------------------------------
                # CHARGEMENT MODÈLES
                # ------------------------------------------------

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
                        load_model(path_critical)
                        if use_critical
                        else None
                    )

                set_status(
                    dossier_id,
                    "En analyse",
                )

                all_results = []

                start_time = time.time()

                # ------------------------------------------------
                # ANALYSE PHOTOS
                # ------------------------------------------------

                progress = st.progress(
                    0,
                    text="Préparation...",
                )

                total_photos = len(photos)

                for index, photo in enumerate(photos):

                    progress.progress(
                        int(
                            (index / total_photos)
                            * 100
                        ),
                        text=(
                            f"Analyse photo "
                            f"{index + 1}/{total_photos}"
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

                # ------------------------------------------------
                # FUSION
                # ------------------------------------------------

                raw_instances = [
                    item
                    for result in all_results
                    for item in result["instances"]
                ]

                if dedup:

                    final_instances = (
                        dedupliquer_instances(
                            raw_instances
                        )
                    )

                else:

                    final_instances = raw_instances

                # ------------------------------------------------
                # REMPLACEMENT
                # ------------------------------------------------

                final_instances = (
                    appliquer_priorite_remplacement(
                        final_instances
                    )
                )

                # ------------------------------------------------
                # AGRÉGATS
                # ------------------------------------------------

                aggregates = (
                    calculer_agregats(
                        final_instances
                    )
                )

                elapsed = (
                    time.time()
                    - start_time
                )

                # ------------------------------------------------
                # SAUVEGARDE SESSION
                # ------------------------------------------------

                st.session_state.analysis = {

                    "results": all_results,

                    "instances": final_instances,

                    "ag": aggregates,

                    "dossier_id": dossier_id,

                    "elapsed": elapsed,
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

    if has_analysis:

        analysis = st.session_state.analysis

        instances = analysis["instances"]

        ag = analysis["ag"]

        st.divider()

        section_header(
            "Résumé de l'analyse",
            "Résultats après fusion et application des règles métier.",
        )

        k1, k2, k3, k4 = st.columns(4)

        render_kpi(
            k1,
            "🧩",
            "Dommages",
            len(instances),
            "Dommages retenus",
        )
        detail_fourniture = calculer_detail_fourniture(instances)

        # ── KPI Fourniture avec avertissement si incomplet ──
        render_kpi(
            k2, "📦", "Pièces (fourniture)",
            f"{detail_fourniture['total_fourniture']:,.0f} MAD",
            (f"⚠️ {detail_fourniture['n_sans_prix']} prix manquant(s)"
            if not detail_fourniture["complet"]
            else f"{detail_fourniture['n_avec_prix']} pièce(s) chiffrée(s)"),
            "orange" if not detail_fourniture["complet"] else "green",
        )

        # ── Détail pièce par pièce ──
        if detail_fourniture["lignes"]:
            section_header("4 · Détail fourniture", "Prix des pièces à remplacer, un par un.")

            if not detail_fourniture["complet"]:
                st.warning(
                    f"⚠️ {detail_fourniture['n_sans_prix']} pièce(s) n'ont pas encore de prix "
                    f"AutoEstimate — le total Fourniture ci-dessus est donc partiel. "
                    f"Clique sur « Récupérer les prix AutoEstimate » ci-dessus."
                )

            rows_fourniture = []
            for ligne in detail_fourniture["lignes"]:
                rows_fourniture.append({
                    "Pièce": ligne["piece"],
                    "Type": ligne["type_piece"] or "—",
                    "Prix": f"{ligne['prix_piece']:,.0f} MAD" if ligne["prix_piece"] is not None else "⚠️ Non récupéré",
                })
            st.dataframe(rows_fourniture, use_container_width=True, hide_index=True)



        render_kpi(
            k3,
            "⚠️",
            "À vérifier",
            ag["n_a_verifier"],
            "Contrôle expert",
            "orange",
        )

        render_kpi(
            k4,
            "🎯",
            "Zones critiques",
            sum(
                1
                for item in instances
                if item.get(
                    "zone_critique_detectee"
                )
            ),
            "Zones détectées",
            "red",
        )

        # ----------------------------------------------------
        # DOMMAGES
        # ----------------------------------------------------

        section_header(
            "Dommages détectés",
            "Chaque ligne représente un dommage retenu par le moteur.",
        )

        if not instances:

            empty_state(
                "✅",
                "Aucun dommage retenu",
                "Les photos ont été analysées mais aucune instance n'a été retenue.",
            )

        else:

            severity_colors = {
                "low": "#28a745",
                "mid": "#ffc107",
                "high": "#dc3545",
            }

            for item in sorted(
                instances,
                key=lambda x: x.get(
                    "score",
                    0,
                ),
                reverse=True,
            ):

                niveau = item.get(
                    "niveau",
                    "mid",
                )

                sev_color = severity_colors.get(
                    niveau,
                    "#6c757d",
                )

                sev_label = LABEL_GRAVITE.get(
                    niveau,
                    str(niveau).capitalize(),
                )

                # --------------------------------------------
                # COÛT — distingue les 3 états possibles d'un
                # remplacement : total connu (vert), MOT connu
                # mais prix pièce encore manquant (orange, avec
                # le montant déjà chiffrable visible), ou rien
                # de connu encore (rouge).
                # --------------------------------------------

                if item.get(
                    "chiffrage_bloque"
                ):

                    cost = (
                        "Inclus dans remplacement"
                    )

                    cost_color = "#6c757d"

                elif item.get(
                    "cout"
                ) is not None:

                    cost = (
                        f"{item['cout']:,.0f} MAD"
                    )

                    cost_color = "#198754"

                elif (
                    item.get("remplacement_requis")
                    and item.get("cout_mot") is not None
                ):

                    cost = (
                        f"MOT: {item['cout_mot']:,.0f} MAD"
                    )

                    cost_color = "#fd7e14"

                elif item.get(
                    "remplacement_requis"
                ):

                    cost = (
                        "Remplacement — "
                        "à chiffrer"
                    )

                    cost_color = "#dc3545"

                else:

                    cost = "À vérifier"

                    cost_color = "#fd7e14"

                # --------------------------------------------
                # ZONE CRITIQUE
                # --------------------------------------------

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

                # --------------------------------------------
                # MOT
                # --------------------------------------------

                mot_html = ""

                heures_mot = item.get(
                    "heures_mot"
                )

                cout_mot = item.get(
                    "cout_mot"
                )

                prix_piece = item.get(
                    "prix_piece"
                )

                if (
                    heures_mot is not None
                    and cout_mot is not None
                ):

                    if prix_piece is not None:

                        mot_html = f"""
                            <div style="
                                margin-top:8px;
                                padding:7px 10px;
                                background:#e7f7ee;
                                border-radius:7px;
                                font-size:10px;
                                color:#0c3158;
                            ">
                                🔧 MOT : {heures_mot:.1f}h × 70 MAD
                                = {cout_mot:,.0f} MAD
                                · 🧩 Pièce ({item.get('type_piece','—')}) :
                                {prix_piece:,.0f} MAD
                            </div>
                        """

                    else:

                        mot_html = f"""
                            <div style="
                                margin-top:8px;
                                padding:7px 10px;
                                background:#eef6ff;
                                border-radius:7px;
                                font-size:10px;
                                color:#0c3158;
                            ">
                                🔧 MOT échange :
                                {heures_mot:.1f}h
                                × 70 MAD
                                = {cout_mot:,.0f} MAD
                                · Prix pièce à récupérer dans l'onglet Chiffrage
                            </div>
                        """

                # --------------------------------------------
                # CARTE
                # --------------------------------------------

                st.markdown(
                    html(
                        f"""
                        <div
                            class="damage-card"
                            style="
                                border-left:
                                4px solid
                                {sev_color};
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
                                        {item.get('type','—')}
                                        <span style="
                                            color:#6c757d;
                                            font-weight:400;
                                        ">
                                            —
                                            {item.get('piece','—')}
                                        </span>
                                    </div>

                                    <div class="damage-meta">
                                        Confiance :
                                        <b>
                                            {item.get('confiance',0)*100:.0f}%
                                        </b>
                                        · Surface :
                                        <b>
                                            {item.get('surface_pct',0):.1f}%
                                        </b>
                                        · Vues :
                                        <b>
                                            {item.get('n_vues',1)}
                                        </b>
                                    </div>

                                    {critical_html}

                                    {mot_html}

                                </div>

                                <div style="
                                    text-align:right;
                                    min-width:160px;
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
                                        font-size:17px;
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

    else:

        empty_state(
            "🤖",
            "Aucune analyse disponible",
            "Clique sur « Lancer / relancer l'analyse IA » pour commencer.",
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

        analysis = st.session_state.analysis

        instances = analysis["instances"]

        ag = analysis["ag"]

        st.markdown(
            html(
                """
                <div class="info-banner">

                    <b>Principe du chiffrage</b><br>

                    • Les réparations utilisent le barème C2.<br>
                    • Les remplacements nécessitent un prix de pièce.<br>
                    • AutoEstimate fournit les observations de prix
                    pour Original / Adaptable / Occasion.<br>
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

                # item_key() vient de core.expertise_engine — c'est LA
                # même fonction utilisée à l'intérieur de
                # enrichir_prix_pieces() pour relire ce choix. Utiliser
                # une clé différente ici ferait que le type choisi ne
                # serait jamais retrouvé, et l'API recevrait toujours
                # "occasion" par défaut sans que rien ne le signale.
                key = item_key(item)

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

                    default_type = "occasion"

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
                        "original": "🟦 Original",
                        "adaptable": "🟨 Adaptable",
                        "occasion": "🟩 Occasion",
                    }.get(x, x),
                    key=f"type_piece_{key}",
                )

                type_choices[key] = chosen

                st.divider()

            # ------------------------------------------------
            # RÉCUPÉRATION AUTOESTIMATE
            # ------------------------------------------------

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
                        "Le dossier ne contient pas "
                        "de marque_id AutoEstimate."
                    )

                elif not model_id:

                    st.error(
                        "Le dossier ne contient pas "
                        "de model_id AutoEstimate."
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
                            ] = calculer_agregats(
                                instances
                            )

                        st.success(
                            "Les prix AutoEstimate ont été mis à jour."
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(
                            f"Erreur AutoEstimate : {e}"
                        )

        else:

            st.success(
                "Aucun remplacement n'a été détecté. "
                "Le chiffrage concerne uniquement les réparations."
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
                        Montant calculé à partir des lignes actuellement chiffrables.
                    </div>

                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        # ====================================================
        # KPI FINANCIERS
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

            if item.get(
                "chiffrage_bloque"
            ):

                cost = "Inclus remplacement"

            elif item.get(
                "cout"
            ) is not None:

                cost = (
                    f"{item['cout']:,.0f} MAD"
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

            else:

                cost = "À vérifier"

            rows.append(
                {
                    "Dommage": item.get(
                        "type",
                        "—",
                    ),
                    "Pièce": item.get(
                        "piece",
                        "—",
                    ),
                    "Gravité": LABEL_GRAVITE.get(
                        item.get(
                            "niveau"
                        ),
                        "—",
                    ),
                    "Action": (
                        "Remplacement"
                        if item.get(
                            "remplacement_requis"
                        )
                        else "Réparation"
                    ),
                    "Coût": cost,
                }
            )

        if rows:

            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True,
            )

        if ag["n_a_verifier"] > 0:

            st.warning(
                f"{ag['n_a_verifier']} ligne(s) "
                "nécessitent encore une validation experte."
            )


# ============================================================
# ONGLET 4 — CONTRÔLE VISUEL
# ============================================================

with tab_controle:

    section_header(
        "Contrôle visuel",
        "Comparer les images originales avec les résultats des modèles IA.",
    )

    if not has_analysis:

        empty_state(
            "🖼️",
            "Aucune visualisation disponible",
            "Lance d'abord l'analyse IA.",
        )

    else:

        analysis = st.session_state.analysis

        for result in analysis["results"]:

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
                    result["img_pieces"],
                    "#18212B",
                ),
                (
                    "Dommages détectés",
                    result["img_dommages"],
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
                        f'<div class="viz-col-title" style="color:{color};">{title}</div>',
                        unsafe_allow_html=True,
                    )

                    # Taille moyenne (pas plein écran), cohérent avec
                    # le reste de l'app — .viz-img plafonne à 340px.
                    st.markdown(
                        html(
                            f'<img src="{array_to_data_uri(array)}" class="viz-img" alt="{title}" />'
                        ),
                        unsafe_allow_html=True,
                    )

            st.divider()


# ============================================================
# PDF
# ============================================================

def generate_pdf(
    meta,
    instances,
    ag,
):

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CabekTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        spaceAfter=10,
    )

    normal = styles["Normal"]

    story = []

    story.append(
        Paragraph(
            "CABEK.AI",
            title_style,
        )
    )

    story.append(
        Paragraph(
            "Rapport d'expertise automobile",
            styles["Heading2"],
        )
    )

    story.append(
        Spacer(
            1,
            8,
        )
    )

    vehicle_data = [
        ["Dossier", meta.get("dossier_id", "—")],
        ["Marque", meta.get("marque", "—")],
        ["Modèle", meta.get("modele", "—")],
        ["Matricule", meta.get("matricule", "—")],
        [
            "Mise en circulation",
            meta.get("annee", "—"),
        ],
    ]

    table = Table(
        vehicle_data,
        colWidths=[
            45 * mm,
            125 * mm,
        ],
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor(
                        "#EAF2FB"
                    ),
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor(
                        "#D9E1EA"
                    ),
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, -1),
                    "Helvetica",
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (0, -1),
                    "Helvetica-Bold",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "PADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
            ]
        )
    )

    story.append(table)

    story.append(
        Spacer(
            1,
            15,
        )
    )

    story.append(
        Paragraph(
            "Synthèse du chiffrage",
            styles["Heading2"],
        )
    )

    total_data = [
        [
            "Total estimé",
            f"{ag['cout_total']:,.0f} MAD",
        ],
        [
            "MO réparation",
            f"{ag['total_mo_reparation']:,.0f} MAD",
        ],
        [
            "Peinture",
            f"{ag['total_mo_peinture']:,.0f} MAD",
        ],
        [
            "Produits peinture",
            f"{ag['total_produit_peinture']:,.0f} MAD",
        ],
        [
            "MOT",
            f"{ag.get('total_mot', 0):,.0f} MAD",
        ],
        [
            "Pièces",
            f"{ag['total_fourniture']:,.0f} MAD",
        ],
    ]

    total_table = Table(
        total_data,
        colWidths=[
            90 * mm,
            80 * mm,
        ],
    )

    total_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor(
                        "#D9E1EA"
                    ),
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor(
                        "#F5F8FB"
                    ),
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (0, -1),
                    "Helvetica-Bold",
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (1, -1),
                    "RIGHT",
                ),
                (
                    "PADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
            ]
        )
    )

    story.append(
        total_table
    )

    story.append(
        Spacer(
            1,
            15,
        )
    )

    story.append(
        Paragraph(
            "Détail des dommages",
            styles["Heading2"],
        )
    )

    damage_rows = [
        [
            "Dommage",
            "Pièce",
            "Gravité",
            "Action",
            "Coût",
        ]
    ]

    for item in instances:

        if item.get(
            "chiffrage_bloque"
        ):

            cost = "Inclus"

        elif item.get(
            "cout"
        ) is not None:

            cost = (
                f"{item['cout']:,.0f}"
            )

        else:

            cost = "À vérifier"

        damage_rows.append(
            [
                str(
                    item.get(
                        "type",
                        "—",
                    )
                ),
                str(
                    item.get(
                        "piece",
                        "—",
                    )
                ),
                str(
                    LABEL_GRAVITE.get(
                        item.get(
                            "niveau"
                        ),
                        "—",
                    )
                ),
                (
                    "Remplacement"
                    if item.get(
                        "remplacement_requis"
                    )
                    else "Réparation"
                ),
                cost,
            ]
        )

    if len(damage_rows) > 1:

        damage_table = Table(
            damage_rows,
            colWidths=[
                32 * mm,
                45 * mm,
                30 * mm,
                32 * mm,
                30 * mm,
            ],
            repeatRows=1,
        )

        damage_table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor(
                            "#0C3158"
                        ),
                    ),
                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, 0),
                        colors.white,
                    ),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, 0),
                        "Helvetica-Bold",
                    ),
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.HexColor(
                            "#D9E1EA"
                        ),
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        8,
                    ),
                ]
            )
        )

        story.append(
            damage_table
        )

    story.append(
        Spacer(
            1,
            15,
        )
    )

    story.append(
        Paragraph(
            "Validation finale : expertise soumise à la validation de l'expert.",
            normal,
        )
    )

    document.build(story)

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

        analysis = st.session_state.analysis

        instances = analysis["instances"]

        ag = analysis["ag"]

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if ag["n_a_verifier"] > 0:

            st.warning(
                f"⚠️ {ag['n_a_verifier']} élément(s) "
                "nécessitent encore une vérification experte."
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
                            Aucun élément bloquant n'a été détecté
                            par le moteur actuel.
                        </div>

                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )

        # ----------------------------------------------------
        # RÉSUMÉ
        # ----------------------------------------------------

        a, b, c = st.columns(3)

        render_kpi(
            a,
            "🧩",
            "Dommages",
            len(instances),
            "Dommages retenus",
        )

        render_kpi(
            b,
            "⚠️",
            "À vérifier",
            ag["n_a_verifier"],
            "Contrôle expert",
            "orange",
        )

        render_kpi(
            c,
            "💰",
            "Total",
            f"{ag['cout_total']:,.0f} MAD",
            "Estimation actuelle",
            "green",
        )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        section_header(
            "Validation de l'expertise",
            "L'expert garde la décision finale.",
        )

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

        st.divider()

        # ----------------------------------------------------
        # PDF
        # ----------------------------------------------------

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
    "provisoire ; l'expert conserve la validation finale."
)