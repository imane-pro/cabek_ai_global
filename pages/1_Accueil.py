import streamlit as st
from core.ui import header
from core.dossier_manager import list_dossiers


def html(content: str) -> str:
    """Retire toute l'indentation, ligne par ligne, pour empêcher Markdown
    d'interpréter le HTML imbriqué comme un bloc de code."""
    return "\n".join(line.strip() for line in content.strip("\n").splitlines())


# ============================================================
# CONFIG
# ============================================================

header(
    "Accueil",
    "Pilotage global du parcours d’expertise automobile"
)

dossiers = list_dossiers()

nb = len(dossiers)

nb_envoyes = sum(
    d.get("status") in {"Envoyé", "En analyse", "À valider"}
    for d in dossiers
)

nb_valides = sum(
    d.get("status") == "Validé"
    for d in dossiers
)

nb_brouillons = sum(
    d.get("status") in {"Brouillon", "Créé"}
    for d in dossiers
)


# ============================================================
# STYLE LOCAL DE LA PAGE
# ============================================================

st.markdown(
    html(
        """
        <style>

        .dashboard-wrap {
            width: 100%;
        }

        /* ============================================================
           KPI CARDS
           ============================================================ */

        .kpi-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 18px;
            min-height: 122px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 16px rgba(15, 35, 60, 0.05);
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

        .kpi-card.green::before {
            background: #16b879;
        }

        .kpi-card.orange::before {
            background: #f0a21a;
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
            font-size: 11px;
            font-weight: 700;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: .04em;
        }

        .kpi-icon {
            width: 32px;
            height: 32px;
            border-radius: 9px;
            background: #edf5ff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 15px;
        }

        .kpi-value {
            margin-top: 13px;
            font-size: 29px;
            line-height: 1;
            font-weight: 850;
            color: #162033;
        }

        .kpi-description {
            margin-top: 8px;
            font-size: 10px;
            color: #8995a6;
        }


        /* ============================================================
           SECTION TITLE
           ============================================================ */

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            margin-top: 28px;
            margin-bottom: 11px;
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
           WORKFLOW
           ============================================================ */

        .workflow {
            background: #ffffff;
            border: 1px solid #e1e8f0;
            border-radius: 15px;
            padding: 21px 18px;
            box-shadow: 0 4px 16px rgba(15, 35, 60, 0.045);
        }

        .workflow-line {
            display: flex;
            align-items: center;
            width: 100%;
        }

        .workflow-step {
            flex: 1;
            display: flex;
            align-items: center;
            min-width: 0;
        }

        .workflow-circle {
            width: 39px;
            height: 39px;
            min-width: 39px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #edf5ff;
            border: 1px solid #cfe3ff;
            color: #1677ff;
            font-weight: 850;
            font-size: 12px;
        }

        .workflow-circle.active {
            background: #1677ff;
            border-color: #1677ff;
            color: #ffffff;
        }

        .workflow-content {
            margin-left: 9px;
        }

        .workflow-title {
            font-size: 11px;
            font-weight: 800;
            color: #172235;
        }

        .workflow-text {
            font-size: 9px;
            color: #8793a5;
            margin-top: 3px;
        }

        .workflow-arrow {
            width: 48px;
            height: 1px;
            background: #d9e1eb;
            position: relative;
            margin: 0 8px;
        }

        .workflow-arrow::after {
            content: "›";
            position: absolute;
            right: -2px;
            top: -9px;
            color: #a9b5c4;
            font-size: 16px;
        }


        /* ============================================================
           INFORMATION CARD
           ============================================================ */

        .info-panel {
            background: linear-gradient(135deg, #071a35 0%, #0c3158 100%);
            border-radius: 15px;
            padding: 20px;
            color: white;
            min-height: 180px;
            position: relative;
            overflow: hidden;
        }

        .info-panel::after {
            content: "";
            position: absolute;
            width: 190px;
            height: 190px;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 50%;
            right: -70px;
            top: -65px;
        }

        .info-title {
            font-size: 16px;
            font-weight: 850;
        }

        .info-text {
            margin-top: 7px;
            font-size: 10px;
            line-height: 1.65;
            color: #b9cbe0;
            max-width: 480px;
        }

        .info-list {
            margin-top: 15px;
        }

        .info-item {
            font-size: 10px;
            color: #d7e4f1;
            margin: 7px 0;
        }

        .info-check {
            color: #43a7ff;
            margin-right: 6px;
        }


        /* ============================================================
           RECENT DOSSIERS
           ============================================================ */

        .dossier-card {
            background: #ffffff;
            border: 1px solid #e1e8f0;
            border-radius: 12px;
            padding: 13px 15px;
            margin-bottom: 7px;
            transition: .15s ease;
        }

        .dossier-card:hover {
            border-color: #bcd9fa;
            box-shadow: 0 4px 14px rgba(15, 50, 90, .06);
        }

        .dossier-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 15px;
        }

        .dossier-main {
            min-width: 0;
        }

        .dossier-id {
            font-size: 11px;
            font-weight: 850;
            color: #172235;
        }

        .dossier-vehicle {
            margin-top: 4px;
            font-size: 9px;
            color: #7b8798;
        }

        .dossier-date {
            font-size: 9px;
            color: #9aa5b4;
            margin-top: 3px;
        }

        .status-pill {
            border-radius: 20px;
            padding: 5px 10px;
            font-size: 8px;
            font-weight: 800;
            white-space: nowrap;
        }

        .status-green {
            color: #087a4e;
            background: #e9fbf3;
            border: 1px solid #c2f0dd;
        }

        .status-orange {
            color: #9b6900;
            background: #fff7df;
            border: 1px solid #f3dfaa;
        }

        .status-blue {
            color: #1262bd;
            background: #edf5ff;
            border: 1px solid #cfe3ff;
        }

        .status-gray {
            color: #687588;
            background: #f2f4f7;
            border: 1px solid #e1e5ea;
        }


        /* ============================================================
           EMPTY STATE
           ============================================================ */

        .empty-state {
            background: #ffffff;
            border: 1px dashed #d4dee9;
            border-radius: 14px;
            padding: 35px;
            text-align: center;
        }

        .empty-icon {
            font-size: 28px;
            margin-bottom: 8px;
        }

        .empty-title {
            font-size: 13px;
            font-weight: 800;
            color: #263246;
        }

        .empty-text {
            font-size: 10px;
            color: #8a96a6;
            margin-top: 5px;
        }


        /* ============================================================
           RESPONSIVE
           ============================================================ */

        @media (max-width: 900px) {

            .workflow-line {
                flex-direction: column;
                align-items: flex-start;
            }

            .workflow-step {
                width: 100%;
                margin-bottom: 10px;
            }

            .workflow-arrow {
                display: none;
            }
        }

        </style>
        """
    ),
    unsafe_allow_html=True
)


# ============================================================
# PAGE CONTAINER
# ============================================================

st.markdown(
    '<div class="dashboard-wrap">',
    unsafe_allow_html=True
)


# ============================================================
# KPI
# ============================================================

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        html(
            f"""
            <div class="kpi-card">
                <div class="kpi-top">
                    <div class="kpi-label">Dossiers</div>
                    <div class="kpi-icon">📁</div>
                </div>
                <div class="kpi-value">{nb}</div>
                <div class="kpi-description">
                    Total des dossiers enregistrés
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True
    )

with c2:
    st.markdown(
        html(
            f"""
            <div class="kpi-card orange">
                <div class="kpi-top">
                    <div class="kpi-label">À traiter</div>
                    <div class="kpi-icon">⏳</div>
                </div>
                <div class="kpi-value">{nb_envoyes}</div>
                <div class="kpi-description">
                    Dossiers envoyés ou en analyse
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True
    )

with c3:
    st.markdown(
        html(
            f"""
            <div class="kpi-card green">
                <div class="kpi-top">
                    <div class="kpi-label">Validés</div>
                    <div class="kpi-icon">✓</div>
                </div>
                <div class="kpi-value">{nb_valides}</div>
                <div class="kpi-description">
                    Expertises validées par un expert
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True
    )

with c4:
    st.markdown(
        html(
            f"""
            <div class="kpi-card dark">
                <div class="kpi-top">
                    <div class="kpi-label">Brouillons</div>
                    <div class="kpi-icon">📝</div>
                </div>
                <div class="kpi-value">{nb_brouillons}</div>
                <div class="kpi-description">
                    Dossiers en cours de collecte
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True
    )


# ============================================================
# PARCOURS CABEK
# ============================================================

st.markdown(
    html(
        """
        <div class="section-header">
            <div>
                <div class="section-title">Parcours CABEK.AI</div>
                <div class="section-subtitle">
                    De la collecte terrain jusqu'à la validation de l'expertise
                </div>
            </div>
        </div>
        """
    ),
    unsafe_allow_html=True
)

st.markdown(
    html(
        """
        <div class="workflow">

            <div class="workflow-line">

                <div class="workflow-step">
                    <div class="workflow-circle active">1</div>
                    <div class="workflow-content">
                        <div class="workflow-title">Collecte</div>
                        <div class="workflow-text">
                            Photos & informations
                        </div>
                    </div>
                </div>

                <div class="workflow-arrow"></div>

                <div class="workflow-step">
                    <div class="workflow-circle active">2</div>
                    <div class="workflow-content">
                        <div class="workflow-title">Réception</div>
                        <div class="workflow-text">
                            Dossier transmis
                        </div>
                    </div>
                </div>

                <div class="workflow-arrow"></div>

                <div class="workflow-step">
                    <div class="workflow-circle">3</div>
                    <div class="workflow-content">
                        <div class="workflow-title">Expertise IA</div>
                        <div class="workflow-text">
                            Pièces & dommages
                        </div>
                    </div>
                </div>

                <div class="workflow-arrow"></div>

                <div class="workflow-step">
                    <div class="workflow-circle">4</div>
                    <div class="workflow-content">
                        <div class="workflow-title">Validation</div>
                        <div class="workflow-text">
                            Contrôle expert
                        </div>
                    </div>
                </div>

                <div class="workflow-arrow"></div>

                <div class="workflow-step">
                    <div class="workflow-circle">5</div>
                    <div class="workflow-content">
                        <div class="workflow-title">Rapport</div>
                        <div class="workflow-text">
                            PDF final
                        </div>
                    </div>
                </div>

            </div>

        </div>
        """
    ),
    unsafe_allow_html=True
)


# ============================================================
# TWO MAIN PANELS
# ============================================================

st.markdown(
    html(
        """
        <div class="section-header">
            <div>
                <div class="section-title">Vue d'ensemble</div>
                <div class="section-subtitle">
                    Les deux interfaces principales du système
                </div>
            </div>
        </div>
        """
    ),
    unsafe_allow_html=True
)

left, right = st.columns([1.05, 1])


with left:

    st.markdown(
        html(
            """
            <div class="info-panel">

                <div class="info-title">
                    📷 Collecte terrain
                </div>

                <div class="info-text">
                    L'agent terrain prépare le dossier et collecte les
                    informations ainsi que les différentes vues du véhicule.
                </div>

                <div class="info-list">

                    <div class="info-item">
                        <span class="info-check">✓</span>
                        Informations véhicule
                    </div>

                    <div class="info-item">
                        <span class="info-check">✓</span>
                        Vues avant, arrière, gauche et droite
                    </div>

                    <div class="info-item">
                        <span class="info-check">✓</span>
                        Photos détaillées des dommages
                    </div>

                    <div class="info-item">
                        <span class="info-check">✓</span>
                        Vérification avant transmission
                    </div>

                </div>

            </div>
            """
        ),
        unsafe_allow_html=True
    )


with right:

    st.markdown(
        html(
            """
            <div class="card" style="
                min-height:180px;
                background:#ffffff;
                border:1px solid #e1e8f0;
                border-radius:15px;
                padding:20px;
            ">

                <div style="
                    font-size:16px;
                    font-weight:850;
                    color:#172235;
                ">
                    🤖 Expertise IA
                </div>

                <div style="
                    font-size:10px;
                    line-height:1.65;
                    color:#7e8b9d;
                    margin-top:7px;
                ">
                    Le bureau reçoit les dossiers, analyse les images,
                    identifie les pièces et dommages, puis applique les
                    règles métier avant validation par l'expert.
                </div>

                <div style="margin-top:15px;">

                    <span class="status-pill status-blue">
                        YOLOv11 Multi-Head
                    </span>

                    <span class="status-pill status-blue">
                        Segmentation
                    </span>

                    <span class="status-pill status-blue">
                        Gravité
                    </span>

                    <span class="status-pill status-blue">
                        C2
                    </span>

                </div>

            </div>
            """
        ),
        unsafe_allow_html=True
    )


# ============================================================
# RECENT DOSSIERS
# ============================================================

st.markdown(
    html(
        """
        <div class="section-header">
            <div>
                <div class="section-title">Derniers dossiers</div>
                <div class="section-subtitle">
                    Suivi des dossiers récemment enregistrés
                </div>
            </div>
        </div>
        """
    ),
    unsafe_allow_html=True
)


if dossiers:

    for d in dossiers[:8]:

        status = d.get("status", "—")

        if status == "Validé":
            status_class = "status-green"

        elif status in {"Envoyé", "En analyse", "À valider"}:
            status_class = "status-orange"

        elif status in {"Brouillon", "Créé"}:
            status_class = "status-gray"

        else:
            status_class = "status-blue"


        dossier_id = d.get("dossier_id", "—")
        marque = d.get("marque", "—")
        modele = d.get("modele", "")
        matricule = d.get("matricule", "—")

        created = d.get("created_at", "")

        st.markdown(
            html(
                f"""
                <div class="dossier-card">

                    <div class="dossier-row">

                        <div class="dossier-main">

                            <div class="dossier-id">
                                {dossier_id}
                            </div>

                            <div class="dossier-vehicle">
                                🚘 {marque} {modele}
                                &nbsp;&nbsp;•&nbsp;&nbsp;
                                Matricule : {matricule}
                            </div>

                            <div class="dossier-date">
                                {created}
                            </div>

                        </div>

                        <div>
                            <span class="status-pill {status_class}">
                                {status}
                            </span>
                        </div>

                    </div>

                </div>
                """
            ),
            unsafe_allow_html=True
        )

else:

    st.markdown(
        html(
            """
            <div class="empty-state">

                <div class="empty-icon">📂</div>

                <div class="empty-title">
                    Aucun dossier pour le moment
                </div>

                <div class="empty-text">
                    Les dossiers créés depuis l'interface de collecte
                    apparaîtront automatiquement ici.
                </div>

            </div>
            """
        ),
        unsafe_allow_html=True
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    html(
        """
        <div style="
            text-align:center;
            color:#9aa6b5;
            font-size:8px;
            margin-top:25px;
            padding-top:12px;
            border-top:1px solid #e4e9ef;
        ">
            CABEK.AI · Plateforme d'expertise automobile assistée par IA
        </div>
        """
    ),
    unsafe_allow_html=True
)

st.markdown("</div>", unsafe_allow_html=True)