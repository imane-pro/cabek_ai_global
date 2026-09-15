import streamlit as st
from PIL import Image

from core.ui import header
from core.dossier_manager import (
    VIEWS,
    create_dossier,
    load_metadata,
    save_uploaded_photo,
    register_photo,
    set_status,
)


# ============================================================
# HEADER
# ============================================================

header(
    "Collecte des données",
    "Création et collecte des photos du véhicule"
)


# ============================================================
# SESSION
# ============================================================

if "dossier_id" not in st.session_state:
    st.session_state.dossier_id = None


# ============================================================
# 1 — INFORMATIONS VEHICULE
# ============================================================

st.markdown(
    '<div class="cabek-section">1 · Informations du véhicule</div>',
    unsafe_allow_html=True
)


with st.form("vehicle_form"):

    c1, c2, c3 = st.columns(3)

    with c1:
        marque = st.text_input(
            "Marque *",
            placeholder="Ex. Toyota"
        )

        modele = st.text_input(
            "Modèle",
            placeholder="Ex. Corolla"
        )

    with c2:
        matricule = st.text_input(
            "Matricule *",
            placeholder="Ex. 12345-A-6"
        )

        expert = st.text_input(
            "Expert / agent",
            placeholder="Nom ou matricule"
        )

    with c3:
        annee = st.text_input(
            "Année",
            placeholder="Ex. 2020"
        )

        type_vehicule = st.selectbox(
            "Type de véhicule",
            [
                "Particulier",
                "Utilitaire",
                "Moto",
                "Autre"
            ]
        )

    start = st.form_submit_button(
        "➕ Créer le dossier",
        use_container_width=True,
        type="primary"
    )


# ============================================================
# CREATION
# ============================================================

if start:

    if not marque.strip():
        st.error("❌ La marque est obligatoire.")

    elif not matricule.strip():
        st.error("❌ Le matricule est obligatoire.")

    else:

        try:

            dossier_id = create_dossier(
                marque=marque,
                matricule=matricule,
                modele=modele,
                expert=expert,
                annee=annee,
                type_vehicule=type_vehicule,
            )

            st.session_state.dossier_id = dossier_id

            st.success(
                f"✅ Dossier créé avec succès : {dossier_id}"
            )

            st.rerun()

        except Exception as e:

            st.error(
                f"❌ Erreur lors de la création du dossier : {e}"
            )


# ============================================================
# SI PAS DE DOSSIER
# ============================================================

if not st.session_state.dossier_id:

    st.info(
        "Crée d'abord le dossier véhicule, "
        "puis ajoute les photos."
    )

    st.stop()


# ============================================================
# DOSSIER ACTUEL
# ============================================================

dossier_id = st.session_state.dossier_id

try:

    metadata = load_metadata(dossier_id)

except Exception as e:

    st.error(
        f"Impossible de charger le dossier : {e}"
    )

    st.stop()


# ============================================================
# CARTE DOSSIER
# ============================================================

st.markdown(
    f"""
    <div class="cabek-card">
        <div class="cabek-card-title">
            📁 Dossier actif
        </div>

        <div style="font-size:24px;font-weight:700;">
            {metadata.get("marque", "")}
            {metadata.get("modele", "")}
        </div>

        <div style="margin-top:8px;">
            Matricule :
            <b>{metadata.get("matricule", "")}</b>
        </div>

        <div style="margin-top:4px;color:#64748b;">
            ID : {dossier_id}
        </div>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# 2 — PHOTOS PRINCIPALES
# ============================================================

st.markdown(
    '<div class="cabek-section">2 · Photos du véhicule</div>',
    unsafe_allow_html=True
)


view_cols = [
    "avant",
    "arriere",
    "gauche",
    "droite"
]


for view in view_cols:

    st.markdown(
        f"### {VIEWS[view]}"
    )

    c1, c2 = st.columns(2)

    with c1:

        camera = st.camera_input(
            f"📷 Prendre une photo — {VIEWS[view]}",
            key=f"cam_{view}"
        )

    with c2:

        upload = st.file_uploader(
            f"📁 Importer — {VIEWS[view]}",
            type=["jpg", "jpeg", "png"],
            key=f"up_{view}"
        )


    # --------------------------------------------------------
    # Camera
    # --------------------------------------------------------

    if camera is not None:

        upload_key = f"saved_camera_{view}"

        if st.session_state.get(upload_key) != camera.file_id:

            try:

                target = save_uploaded_photo(
                    dossier_id,
                    view,
                    camera,
                    index=1
                )

                register_photo(
                    dossier_id,
                    view,
                    target
                )

                st.session_state[upload_key] = camera.file_id

                st.success(
                    f"✅ {VIEWS[view]} enregistrée"
                )

            except Exception as e:

                st.error(
                    f"Erreur : {e}"
                )


    # --------------------------------------------------------
    # Upload
    # --------------------------------------------------------

    if upload is not None:

        upload_key = f"saved_upload_{view}"

        upload_id = (
            f"{upload.name}_"
            f"{upload.size}"
        )

        if st.session_state.get(upload_key) != upload_id:

            try:

                target = save_uploaded_photo(
                    dossier_id,
                    view,
                    upload,
                    index=1
                )

                register_photo(
                    dossier_id,
                    view,
                    target
                )

                st.session_state[upload_key] = upload_id

                st.success(
                    f"✅ {VIEWS[view]} enregistrée"
                )

            except Exception as e:

                st.error(
                    f"Erreur : {e}"
                )


# ============================================================
# 3 — DETAILS
# ============================================================

st.markdown(
    '<div class="cabek-section">3 · Détails des dommages</div>',
    unsafe_allow_html=True
)


details = st.file_uploader(
    "Ajouter une ou plusieurs photos de détail",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key="details"
)


if details:

    for i, f in enumerate(details, start=1):

        detail_key = (
            f"detail_{f.name}_{f.size}"
        )

        if not st.session_state.get(detail_key):

            try:

                target = save_uploaded_photo(
                    dossier_id,
                    "details",
                    f,
                    index=i
                )

                register_photo(
                    dossier_id,
                    "details",
                    target
                )

                st.session_state[detail_key] = True

            except Exception as e:

                st.error(
                    f"Erreur photo détail : {e}"
                )


# ============================================================
# VERIFICATION
# ============================================================

metadata = load_metadata(
    dossier_id
)

photos = metadata.get(
    "photos",
    []
)


counts = {
    v: sum(
        p.get("view") == v
        for p in photos
    )
    for v in VIEWS
}


st.markdown(
    '<div class="cabek-section">4 · Vérification du dossier</div>',
    unsafe_allow_html=True
)


cols = st.columns(5)

for col, view in zip(cols, VIEWS):

    with col:

        st.metric(
            VIEWS[view],
            counts[view]
        )


required_ok = all(
    counts[v] >= 1
    for v in view_cols
)


if required_ok:

    st.success(
        "✅ Les 4 vues principales sont présentes."
    )

else:

    missing = ", ".join(
        VIEWS[v]
        for v in view_cols
        if counts[v] == 0
    )

    st.warning(
        f"⚠️ Vues principales manquantes : {missing}"
    )


# ============================================================
# ENVOI EXPERTISE
# ============================================================

if st.button(
    "📤 Envoyer le dossier à l'expertise IA",
    use_container_width=True,
    type="primary",
    disabled=not required_ok
):

    set_status(
        dossier_id,
        "Envoyé"
    )

    st.success(
        "✅ Dossier envoyé à l'expertise IA."
    )

    st.info(
        "Ouvre « Expertise IA » dans la barre latérale."
    )