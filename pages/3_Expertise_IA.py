import io
import time
import base64
from pathlib import Path
from core.ui import header

import streamlit as st
from PIL import Image
from ultralytics import YOLO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from core.dossier_manager import list_dossiers, load_metadata, photo_paths, set_status, dossier_path
from core.expertise_engine import (
    analyser, dedupliquer_instances, appliquer_priorite_remplacement,
    calculer_agregats, CATEGORIES_MARQUE, LABEL_GRAVITE,
)
from bareme_c2 import TARIF_REPARATION_DH, TARIF_MOP_DH


def html(content: str) -> str:
    """Retire toute l'indentation, ligne par ligne, et supprime les lignes
    vides. Les lignes vides sont dangereuses : une variable conditionnelle
    insérée seule sur sa ligne (ex. {crit_html} == "") laisse une ligne
    blanche au milieu du bloc HTML, et Markdown considère alors que le
    bloc HTML brut est terminé — tout ce qui suit est reparsé et retombe
    dans un bloc de code."""
    lines = (line.strip() for line in content.strip("\n").splitlines())
    return "\n".join(line for line in lines if line)


def file_to_data_uri(path) -> str:
    """Encode un fichier image en data URI, pour l'injecter dans un <img>
    au sein d'un seul bloc HTML — évite de mélanger st.image (qui crée son
    propre conteneur DOM séparé) avec un <div> ouvert/fermé sur deux
    appels st.markdown distincts, ce qui casse l'imbrication réelle."""
    data = Path(path).read_bytes()
    ext = Path(path).suffix.lstrip(".").lower()
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    return f"data:image/{mime};base64,{base64.b64encode(data).decode()}"


def array_to_data_uri(arr, fmt: str = "JPEG") -> str:
    """Même principe que file_to_data_uri, pour une image en mémoire
    (tableau numpy retourné par res.plot())."""
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format=fmt)
    mime = "jpeg" if fmt.upper() == "JPEG" else fmt.lower()
    return f"data:image/{mime};base64,{base64.b64encode(buf.getvalue()).decode()}"


@st.cache_resource(show_spinner=False)
def load_model(path: str):
    return YOLO(path)


# ============================================================
# STATUTS → BADGE
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
    return STATUS_CLASSES.get(status, "status-blue")


def section_header(title: str, subtitle: str = "") -> None:
    sub = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        html(f"""
        <div class="section-header">
            <div>
                <div class="section-title">{title}</div>
                {sub}
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )


def render_kpi(col, icon: str, label: str, value, description: str, variant: str = "") -> None:
    col.markdown(
        html(f"""
        <div class="kpi-card {variant}">
            <div class="kpi-top">
                <div class="kpi-label">{label}</div>
                <div class="kpi-icon">{icon}</div>
            </div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-description">{description}</div>
        </div>
        """),
        unsafe_allow_html=True,
    )


header("Expertise IA", "Analyse, détection des dommages et estimation des coûts")

dossiers = list_dossiers()
if not dossiers:
    st.info("Aucun dossier dans data/dossiers. Passe d'abord par « Collecte des données » pour créer un dossier.")
    st.stop()


# ============================================================
# STYLE DE LA PAGE
# ============================================================

st.markdown(
    html(
        """
        <style>

        /* ============================================================
           KPI CARDS (identique à la page Accueil, pour la cohérence)
           ============================================================ */

        .kpi-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 18px;
            min-height: 110px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 16px rgba(15, 35, 60, 0.05);
            margin-bottom: 6px;
        }

        .kpi-card::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
            background: #1677ff;
        }

        .kpi-card.green::before  { background: #16b879; }
        .kpi-card.orange::before { background: #f0a21a; }
        .kpi-card.dark::before   { background: #344054; }
        .kpi-card.red::before    { background: #dc3545; }

        .kpi-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .kpi-label {
            font-size: 11px;
            font-weight: 700;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: .04em;
        }

        .kpi-icon {
            width: 30px;
            height: 30px;
            border-radius: 9px;
            background: #edf5ff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
        }

        .kpi-value {
            margin-top: 11px;
            font-size: 24px;
            line-height: 1.15;
            font-weight: 850;
            color: #162033;
            word-break: break-word;
        }

        .kpi-description {
            margin-top: 6px;
            font-size: 10px;
            color: #8995a6;
        }

        /* ============================================================
           SECTION HEADERS
           ============================================================ */

        .section-header {
            margin-top: 30px;
            margin-bottom: 12px;
        }

        .section-title {
            font-size: 16px;
            font-weight: 850;
            color: #172235;
        }

        .section-subtitle {
            font-size: 10px;
            color: #8491a3;
            margin-top: 2px;
        }

        /* ============================================================
           CARTE DOSSIER SÉLECTIONNÉ
           ============================================================ */

        .selected-card {
            background: linear-gradient(135deg, #071a35 0%, #0c3158 100%);
            border-radius: 15px;
            padding: 20px 22px;
            color: #ffffff;
            position: relative;
            overflow: hidden;
        }

        .selected-card::after {
            content: "";
            position: absolute;
            width: 170px;
            height: 170px;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 50%;
            right: -60px;
            top: -55px;
        }

        .selected-eyebrow {
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
            color: #8fb4e0;
        }

        .selected-title {
            font-size: 19px;
            font-weight: 850;
            margin-top: 6px;
        }

        .selected-sub {
            margin-top: 6px;
            font-size: 11px;
            color: #b9cbe0;
        }

        /* ============================================================
           STATUS PILL
           ============================================================ */

        .status-pill {
            display: inline-block;
            border-radius: 20px;
            padding: 4px 11px;
            font-size: 9px;
            font-weight: 800;
            white-space: nowrap;
            margin-top: 10px;
        }

        .status-green  { color: #a9f4d6; background: rgba(22,184,121,.18); border: 1px solid rgba(22,184,121,.4); }
        .status-orange { color: #ffdf9e; background: rgba(240,162,26,.18); border: 1px solid rgba(240,162,26,.4); }
        .status-blue   { color: #bcdcff; background: rgba(22,119,255,.18); border: 1px solid rgba(22,119,255,.4); }
        .status-gray   { color: #d6dde6; background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.25); }

        /* ============================================================
           GALERIE PHOTO — vignettes de taille moyenne
           ============================================================ */

        .photo-card {
            background: #ffffff;
            border: 1px solid #e9ecef;
            border-radius: 12px;
            padding: 12px 12px 14px 12px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(15, 35, 60, 0.04);
            margin-bottom: 16px;
        }

        .photo-title {
            margin-top: 10px;
            font-size: 12px;
            font-weight: 800;
            color: #172235;
        }

        .photo-filename {
            font-size: 9px;
            color: #9aa5b4;
            margin-top: 2px;
        }

        /* Photo unique agrandie (sélecteur déroulant) — pas de crop */
        .photo-img {
            max-width: 100%;
            max-height: 420px;
            border-radius: 8px;
            object-fit: contain;
            display: block;
            margin: 0 auto;
        }

        /* Images de visualisation IA — taille moyenne, alignées */
        .viz-img {
            width: 100%;
            max-width: 320px;
            border-radius: 8px;
            display: block;
            margin: 0 auto;
        }

        /* ============================================================
           CARTES DOMMAGE
           ============================================================ */

        .damage-card {
            background: #ffffff;
            border: 1px solid #e9ecef;
            border-radius: 10px;
            padding: 16px 18px;
            margin-bottom: 12px;
            box-shadow: 0 2px 8px rgba(15, 35, 60, 0.04);
        }

        .damage-title {
            font-size: 1.02rem;
            font-weight: 700;
            color: #172235;
        }

        .damage-meta {
            font-size: 0.82rem;
            color: #6c757d;
            margin-top: 4px;
        }

        .sev-pill {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 0.78rem;
        }

        /* ============================================================
           CARTES VISUALISATION IA
           ============================================================ */

        .viz-card {
            background: #ffffff;
            border: 1px solid #e9ecef;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 18px;
            box-shadow: 0 2px 8px rgba(15, 35, 60, 0.04);
        }

        .viz-photo-name {
            font-size: 0.95rem;
            font-weight: 700;
            color: #172235;
            margin-bottom: 10px;
        }

        .viz-col-title {
            text-align: center;
            font-size: 0.82rem;
            font-weight: 700;
            color: #18212B;
            margin-bottom: 6px;
        }

        </style>
        """
    ),
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown("### 📂 Dossier à analyser")
    labels = [f"{d['dossier_id']} · {d.get('matricule','')} · {d.get('status','')}" for d in dossiers]
    selected_idx = st.selectbox("Sélectionner un dossier", range(len(dossiers)), format_func=lambda i: labels[i])
    selected = dossiers[selected_idx]

    st.divider()
    st.markdown("### ⚙️ Paramètres IA")
    path_pieces = st.text_input("Modèle pièces", "models/best_pieces.pt")
    path_dommages = st.text_input("Modèle dommages", "models/best.pt")
    use_critical = st.checkbox("Activer zone critique", True)
    path_critical = st.text_input("Modèle zone critique", "models/best_zone_critique.pt", disabled=not use_critical)
    conf_pieces = st.slider("Confiance pièces", .05, .95, .25, .05)
    conf_dommages = st.slider("Confiance dommages", .05, .95, .15, .05)
    iou_min = st.slider("Association dommage ↔ pièce", 0.0, .5, .05, .01)
    conf_critical = st.slider("Confiance zone critique", .05, .95, .25, .05) if use_critical else .25
    critical_threshold = st.slider("Seuil intersection zone critique", 0.0, .5, .05, .01) if use_critical else .05
    dedup = st.checkbox("Fusionner les vues multiples", True)

meta = load_metadata(selected["dossier_id"])
photos = photo_paths(selected["dossier_id"])


# ============================================================
# CARTE DOSSIER SÉLECTIONNÉ
# ============================================================

st.markdown(
    html(f"""
    <div class="selected-card">
        <div class="selected-eyebrow">Dossier sélectionné</div>
        <div class="selected-title">{meta.get("marque","—")} {meta.get("modele","")}</div>
        <div class="selected-sub">Matricule {meta.get("matricule","—")} · {len(photos)} photo(s)</div>
        <span class="status-pill {status_class(meta.get('status',''))}">{meta.get("status","—")}</span>
    </div>
    """),
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
render_kpi(c1, "🔖", "Matricule", meta.get("matricule", "—"), "Immatriculation du véhicule")
render_kpi(c2, "🚘", "Marque", meta.get("marque", "—"), meta.get("modele", "") or "Modèle non renseigné", "dark")
render_kpi(c3, "📷", "Photos", len(photos), "Vues enregistrées dans le dossier")
render_kpi(c4, "📌", "Statut", meta.get("status", "—"), "État courant du dossier", "orange")


# ---------------------------------------------------------
# 1 · Dossier photo — sélecteur déroulant, une photo à la fois
# ---------------------------------------------------------
section_header("1 · Dossier photo", "Vues du véhicule enregistrées lors de la collecte")

if photos:
    photo_labels = [f"{p.get('view_label', p.get('view'))} · {p['filename']}" for p in photos]
    photo_idx = st.selectbox(
        "Choisir une photo à afficher",
        range(len(photos)),
        format_func=lambda i: photo_labels[i],
        key="photo_viewer_select",
    )
    p = photos[photo_idx]
    photo_uri = file_to_data_uri(p["full_path"])

    left_pad, mid, right_pad = st.columns([1, 2, 1])
    with mid:
        st.markdown(
            html(f"""
            <div class="photo-card">
                <img src="{photo_uri}" class="photo-img" alt="{p.get('view_label', p.get('view'))}" />
                <div class="photo-title">{p.get('view_label', p.get('view'))}</div>
                <div class="photo-filename">{p['filename']}</div>
            </div>
            """),
            unsafe_allow_html=True,
        )
else:
    st.info("Aucune photo dans ce dossier.")

# ---------------------------------------------------------
# 2 · Analyse IA
# ---------------------------------------------------------
section_header("2 · Analyse IA", "Lance la détection pièces / dommages / zones critiques")

if st.button("🚀 Lancer l'analyse IA", type="primary", use_container_width=True):
    try:
        with st.spinner("Chargement des heads YOLOv11..."):
            model_p = load_model(path_pieces)
            model_d = load_model(path_dommages)
            model_z = load_model(path_critical) if use_critical else None
        set_status(selected["dossier_id"], "En analyse")
        all_results = []
        t0 = time.time()
        with st.spinner(f"Analyse de {len(photos)} photo(s)..."):
            for p in photos:
                img = Image.open(p["full_path"]).convert("RGB")
                r = analyser(model_p, model_d, __import__("numpy").array(img), conf_pieces, conf_dommages, iou_min,
                             meta.get("marque", ""), p["filename"], model_z, conf_critical, critical_threshold)
                all_results.append(r)
        raw = [x for r in all_results for x in r["instances"]]
        final = dedupliquer_instances(raw) if dedup else raw
        final = appliquer_priorite_remplacement(final)
        ag = calculer_agregats(final)
        st.session_state.analysis = {"results": all_results, "instances": final, "ag": ag, "dossier_id": selected["dossier_id"], "elapsed": time.time()-t0}
        set_status(selected["dossier_id"], "À valider")
        st.success(f"Analyse terminée en {time.time()-t0:.1f}s")
    except Exception as e:
        st.error(f"Impossible de lancer l'analyse : {e}")

if "analysis" not in st.session_state or st.session_state.analysis.get("dossier_id") != selected["dossier_id"]:
    st.info("Clique sur « Lancer l'analyse IA » pour générer les résultats.")
    st.stop()

analysis = st.session_state.analysis
instances = analysis["instances"]
ag = analysis["ag"]

# ---------------------------------------------------------
# 3 · Résultats de l'expertise
# ---------------------------------------------------------
section_header("3 · Résultats de l'expertise", "Synthèse après fusion des vues et application des règles métier")

k1, k2, k3, k4 = st.columns(4)
render_kpi(k1, "🧩", "Dommages fusionnés", len(instances), "Après déduplication multi-vues")
render_kpi(k2, "🔩", "Pièces détectées", sum(r["n_pieces"] for r in analysis["results"]), "Toutes photos confondues", "dark")
render_kpi(k3, "💰", "Coût estimé C2", f"{ag['cout_total']:,.0f} MAD", "Barème C2 — hors remplacement", "green")
render_kpi(k4, "⚠️", "À vérifier", ag["n_a_verifier"], "Lignes nécessitant un contrôle expert", "orange")

# ---------------------------------------------------------
# Détail des dommages
# ---------------------------------------------------------
section_header("Détail des dommages")

SEV_COLORS = {"low": "#28a745", "mid": "#ffc107", "high": "#dc3545"}

for item in sorted(instances, key=lambda x: x.get("score", 0), reverse=True):
    sev = item["niveau"]

    if item.get("chiffrage_bloque"):
        cost = "Inclus dans remplacement"
        cost_color = "#6c757d"
    elif item.get("remplacement_requis"):
        cost = "Remplacement — à chiffrer"
        cost_color = "#dc3545"
    elif item.get("cout") is not None:
        cost = f"{item['cout']:,.0f} MAD"
        cost_color = "#198754"
    else:
        cost = "À vérifier"
        cost_color = "#fd7e14"

    crit_html = (
        f'<div style="margin-top:8px; padding:6px 10px; background:#fff3cd; color:#856404; '
        f'border-radius:6px; font-size:0.85rem; display:inline-flex; align-items:center; gap:6px;">'
        f'🎯 Zone critique bosse · {item.get("zone_critique_overlap_pct",0):.0f}% · remplacement</div>'
    ) if item.get("zone_critique_detectee") else ""

    sev_color = SEV_COLORS.get(sev, "#6c757d")
    sev_label = LABEL_GRAVITE.get(sev, str(sev).capitalize())

    st.markdown(
        html(f"""
        <div class="damage-card" style="border-left:4px solid {sev_color};">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px;">
                <div style="flex:1; min-width:250px;">
                    <div class="damage-title">
                        {item['type']} <span style="color:#6c757d; font-weight:400;">— {item['piece']}</span>
                    </div>
                    <div class="damage-meta">
                        Confiance: <b>{item['confiance']*100:.0f}%</b> · Surface: <b>{item['surface_pct']:.1f}%</b> · Vues: <b>{item.get('n_vues',1)}</b>
                    </div>
                    {crit_html}
                </div>
                <div style="text-align:right; min-width:150px;">
                    <span class="sev-pill" style="background:{sev_color}15; color:{sev_color};">
                        {sev_label}
                    </span>
                    <div style="margin-top:8px; font-size:1.1rem; font-weight:700; color:{cost_color};">
                        {cost}
                    </div>
                </div>
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------
# Génération PDF (inchangé)
# ---------------------------------------------------------
def generate_pdf(meta, instances, ag):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=14*mm, leftMargin=14*mm, topMargin=16*mm, bottomMargin=14*mm, title="Rapport CABEK")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("CabekTitle", parent=styles["Title"], fontSize=20, leading=24, alignment=TA_CENTER, textColor=colors.HexColor("#18212B"))
    normal = ParagraphStyle("CabekNormal", parent=styles["Normal"], fontSize=8.5, leading=12, textColor=colors.HexColor("#26313B"))
    story = [Paragraph("CABEK", title), Paragraph("RAPPORT D'EXPERTISE AUTOMOBILE — IA", title), Spacer(1, 5*mm)]
    info = [["Dossier", meta.get("dossier_id","—"), "Statut", meta.get("status","—")], ["Matricule", meta.get("matricule","—"), "Marque", meta.get("marque","—")], ["Modèle", meta.get("modele","—"), "Photos", str(len(photo_paths(meta["dossier_id"])))]]
    table = Table(info, colWidths=[28*mm, 55*mm, 28*mm, 55*mm])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F3F5F7")),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#D9DEE3")),("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),("FONTNAME",(2,0),(2,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    story += [table, Spacer(1, 6*mm), Paragraph("SYNTHÈSE", styles["Heading2"])]
    story.append(Paragraph(f"{len(instances)} dommage(s) détecté(s) après fusion des vues. Coût automatiquement chiffrable : <b>{ag['cout_total']:,.0f} MAD</b>. Lignes à vérifier : <b>{ag['n_a_verifier']}</b>.", normal))
    story += [Spacer(1, 5*mm), Paragraph("DÉTAIL DES DOMMAGES", styles["Heading2"])]
    rows=[["#","Dommage","Pièce","Gravité","Conf.","Coût"]]
    for i,it in enumerate(sorted(instances,key=lambda x:x.get("score",0),reverse=True),1):
        if it.get("chiffrage_bloque"): cost="Inclus remplacement"
        elif it.get("remplacement_requis"): cost="Remplacement / manuel"
        elif it.get("cout") is not None: cost=f"{it['cout']:,.0f} MAD"
        else: cost="À vérifier"
        rows.append([str(i),it.get("type","—"),it.get("piece","—"),LABEL_GRAVITE.get(it.get("niveau"),"—"),f"{it.get('confiance',0)*100:.0f}%",cost])
    dt=Table(rows,colWidths=[8*mm,35*mm,48*mm,25*mm,20*mm,30*mm],repeatRows=1)
    dt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#18212B")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#D9DEE3")),("FONTSIZE",(0,0),(-1,-1),7.5),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(4,1),(-1,-1),"RIGHT"),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story += [dt, Spacer(1,6*mm), Paragraph("DÉCOMPOSITION DU COÛT", styles["Heading2"])]
    cost_rows=[["MO Tôlerie",f"{ag['total_mo_reparation']:,.0f} MAD"],["MOP Peinture",f"{ag['total_mo_peinture']:,.0f} MAD"],["MET",f"{ag['total_produit_peinture']:,.0f} MAD"],["Fourniture",f"{ag['total_fourniture']:,.0f} MAD"],["TOTAL ESTIMÉ",f"{ag['cout_total']:,.0f} MAD"]]
    ct=Table(cost_rows,colWidths=[125*mm,40*mm])
    ct.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.4,colors.HexColor("#D9DEE3")),("ALIGN",(1,0),(1,-1),"RIGHT"),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#F3F5F7")),("FONTSIZE",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    story += [ct, Spacer(1,6*mm), Paragraph("Avertissement : ce rapport est une aide au diagnostic. Les détections, la gravité, l'action et l'estimation doivent être contrôlées et validées par un expert automobile avant décision.", normal)]
    doc.build(story)
    return buffer.getvalue()

# ---------------------------------------------------------
# Décomposition du coût
# ---------------------------------------------------------
section_header("💰 Décomposition du coût", "Répartition du chiffrage automatique par poste")

a, b, c, d = st.columns(4)
render_kpi(a, "🔧", "MO Tôlerie", f"{ag['total_mo_reparation']:,.0f} MAD", "Main-d'œuvre réparation")
render_kpi(b, "🎨", "MOP Peinture", f"{ag['total_mo_peinture']:,.0f} MAD", "Main-d'œuvre peinture", "dark")
render_kpi(c, "🧴", "MET", f"{ag['total_produit_peinture']:,.0f} MAD", "Matériel / produit peinture")
render_kpi(d, "📦", "Fourniture", f"{ag['total_fourniture']:,.0f} MAD", "Hors barème actuel", "orange")

# ---------------------------------------------------------
# Visualisations IA — images de taille moyenne
# ---------------------------------------------------------
section_header("🖼️ Visualisations IA", "Détections superposées, par photo source")

for r in analysis["results"]:
    blocks = [("Pièces détectées", r["img_pieces"], "#18212B")]
    blocks.append(("Dommages détectés", r["img_dommages"], "#18212B"))
    if r.get("img_zones_critiques") is not None:
        blocks.append(("Zone critique", r["img_zones_critiques"], "#dc3545"))

    cols_html = "".join(
        f"""
        <div style="flex:1; min-width:220px;">
            <div class="viz-col-title" style="color:{color};">{title}</div>
            <img src="{array_to_data_uri(arr)}" class="viz-img" alt="{title}" />
        </div>
        """
        for title, arr, color in blocks
    )

    st.markdown(
        html(f"""
        <div class="viz-card">
            <div class="viz-photo-name">📸 {r.get("nom","Photo")}</div>
            <div style="display:flex; gap:16px; flex-wrap:wrap;">
                {cols_html}
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )

st.markdown("---")

if st.button("✅ Valider l'expertise", use_container_width=True, type="primary"):
    set_status(selected["dossier_id"], "Validé")
    st.success("Expertise marquée comme validée.")

section_header("📄 Rapport", "Génère le rapport PDF final de l'expertise")

pdf = generate_pdf(meta, instances, ag)
st.download_button("📄 Télécharger le rapport PDF", data=pdf, file_name=f"rapport_{meta['dossier_id']}.pdf", mime="application/pdf", use_container_width=True)

st.caption("Règle importante : la zone critique est utilisée ici uniquement pour les bosses. Une bosse qui chevauche la zone critique devient grave et impose le remplacement. Les autres types de dommages suivent leurs propres règles métier.")