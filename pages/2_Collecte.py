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

from core.parts_pricing import (
    get_marques,
    get_models,
    AutoEstimateError,
)


# ============================================================
# HEADER
# ============================================================

header(
    "Collecte des données",
    "Création d'un dossier photo pour expertise IA"
)


# ============================================================
# SESSION STATE
# ============================================================

if "dossier_id" not in st.session_state:
    st.session_state.dossier_id = None


# ============================================================
# RÉCUPÉRATION DES MARQUES AUTOESTIMATE
# ============================================================

api_disponible = True
marques = []

try:
    marques = get_marques()

except AutoEstimateError as e:

    api_disponible = False

    st.warning(
        f"API AutoEstimate indisponible : {e}\n\n"
        "La saisie manuelle de la marque et du modèle reste disponible. "
        "Les prix automatiques ne seront pas disponibles pour ce dossier."
    )


# ============================================================
# 1. INFORMATIONS DU VÉHICULE
# ============================================================

st.markdown(
    '<div class="cabek-section">1 · Informations du véhicule</div>',
    unsafe_allow_html=True,
)


c1, c2 = st.columns(2)


# Valeurs par défaut
marque = ""
modele = ""
marque_id = None
model_id = None


# ============================================================
# COLONNE GAUCHE
# MARQUE + MODÈLE
# ============================================================

with c1:

    if api_disponible and marques:

        # ----------------------------------------------------
        # MARQUES
        # ----------------------------------------------------

        marque_options = [
            m["libelle"]
            for m in marques
        ]

        marque_libelle = st.selectbox(
            "Marque *",
            options=marque_options,
            index=None,
            placeholder="Choisir une marque",
            key="collecte_marque",
        )

        # ----------------------------------------------------
        # MARQUE SÉLECTIONNÉE
        # ----------------------------------------------------

        if marque_libelle:

            marque = marque_libelle

            marque_id = next(
                (
                    m["id"]
                    for m in marques
                    if m["libelle"] == marque_libelle
                ),
                None,
            )

        # ----------------------------------------------------
        # MODÈLES
        # ----------------------------------------------------

        modeles = []

        if marque_id is not None:

            try:

                modeles = get_models(marque_id)

            except AutoEstimateError as e:

                st.error(
                    f"Impossible de récupérer les modèles "
                    f"pour {marque_libelle} : {e}"
                )

        # ----------------------------------------------------
        # SELECT MODÈLE
        # ----------------------------------------------------

        if modeles:

            modele_options = [
                m["libelle"]
                for m in modeles
            ]

            modele_libelle = st.selectbox(
                "Modèle *",
                options=modele_options,
                index=None,
                placeholder="Choisir un modèle",
                key=f"collecte_modele_{marque_id}",
            )

            if modele_libelle:

                modele = modele_libelle

                model_id = next(
                    (
                        m["id"]
                        for m in modeles
                        if m["libelle"] == modele_libelle
                    ),
                    None,
                )

        elif marque_id is not None:

            st.warning(
                "Aucun modèle trouvé pour cette marque "
                "dans AutoEstimate."
            )

        else:

            st.selectbox(
                "Modèle *",
                options=[],
                disabled=True,
                placeholder="Choisir d'abord une marque",
                key="collecte_modele_disabled",
            )

    # ========================================================
    # FALLBACK : API INDISPONIBLE
    # ========================================================

    else:

        marque = st.text_input(
            "Marque *",
            placeholder="Ex. Toyota",
            key="collecte_marque_manuel",
        )

        modele = st.text_input(
            "Modèle",
            placeholder="Ex. Corolla",
            key="collecte_modele_manuel",
        )


# ============================================================
# COLONNE DROITE
# ANNÉE + MATRICULE
# ============================================================

with c2:

    annee = st.text_input(
        "Année (date de mise en circulation) *",
        placeholder="Ex. 2020",
        key="collecte_annee",
    )

    matricule = st.text_input(
        "Matricule *",
        placeholder="Ex. 12345-A-6",
        key="collecte_matricule",
    )


# ============================================================
# CRÉER LE DOSSIER
# ============================================================

start = st.button(
    "Créer le dossier",
    use_container_width=True,
    type="primary",
)


if start:

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not marque.strip():

        st.error(
            "La marque est obligatoire."
        )

    elif api_disponible and marque_id is None:

        st.error(
            "Veuillez sélectionner une marque."
        )

    elif api_disponible and model_id is None:

        st.error(
            "Veuillez sélectionner un modèle."
        )

    elif not matricule.strip():

        st.error(
            "Le matricule est obligatoire."
        )

    elif not annee.strip():

        st.error(
            "L'année est obligatoire."
        )

    elif not annee.strip().isdigit():

        st.error(
            "L'année doit être un nombre, par exemple 2020."
        )

    elif len(annee.strip()) != 4:

        st.error(
            "L'année doit contenir 4 chiffres, par exemple 2020."
        )

    else:

        # ----------------------------------------------------
        # CRÉATION DU DOSSIER
        # ----------------------------------------------------

        try:

            st.session_state.dossier_id = create_dossier(
                marque=marque,
                matricule=matricule,
                modele=modele,
                annee=annee,
                marque_id=marque_id,
                model_id=model_id,
            )

            st.success(
                f"Dossier créé : "
                f"{st.session_state.dossier_id}"
            )

            # ------------------------------------------------
            # INFORMATION SI API NON DISPONIBLE
            # ------------------------------------------------

            if marque_id is None:

                st.info(
                    "Ce dossier n'a pas de marque_id AutoEstimate. "
                    "Les prix automatiques ne seront pas disponibles."
                )

        except Exception as e:

            st.error(
                f"Erreur lors de la création du dossier : {e}"
            )


# ============================================================
# SI AUCUN DOSSIER
# ============================================================

if not st.session_state.dossier_id:

    st.info(
        "Crée d'abord le dossier véhicule, "
        "puis ajoute les photos guidées."
    )

    st.stop()


# ============================================================
# DOSSIER ACTUEL
# ============================================================

dossier_id = st.session_state.dossier_id

metadata = load_metadata(dossier_id)


# ============================================================
# 2. PHOTOS DU VÉHICULE
# ============================================================

st.markdown(
    '<div class="cabek-section">2 · Photos du véhicule</div>',
    unsafe_allow_html=True,
)


st.caption(
    f"Dossier {dossier_id} · "
    f"{metadata.get('marque', '')} "
    f"{metadata.get('modele', '')} "
    f"({metadata.get('annee', '—')}) · "
    f"Matricule {metadata.get('matricule', '')}"
)


view_cols = [
    "avant",
    "arriere",
    "gauche",
    "droite",
]


for view in view_cols:

    st.markdown(
        f"#### {VIEWS[view]}"
    )

    c1, c2 = st.columns(2)

    # --------------------------------------------------------
    # CAMERA
    # --------------------------------------------------------

    with c1:

        camera = st.camera_input(
            f"Prendre {VIEWS[view]}",
            key=f"cam_{view}",
        )

    # --------------------------------------------------------
    # UPLOAD
    # --------------------------------------------------------

    with c2:

        upload = st.file_uploader(
            f"Importer — {VIEWS[view]}",
            type=[
                "jpg",
                "jpeg",
                "png",
            ],
            key=f"up_{view}",
        )

    # --------------------------------------------------------
    # PHOTO SÉLECTIONNÉE
    # --------------------------------------------------------

    selected = camera or upload

    if selected is not None:

        target = save_uploaded_photo(
            dossier_id,
            view,
            selected,
            index=1,
        )

        register_photo(
            dossier_id,
            view,
            target,
        )

        st.image(
            Image.open(target),
            caption=VIEWS[view],
            width=420,
        )


# ============================================================
# 3. DÉTAILS DES DOMMAGES
# ============================================================

st.markdown(
    '<div class="cabek-section">3 · Détails des dommages</div>',
    unsafe_allow_html=True,
)


details = st.file_uploader(
    "Ajouter une ou plusieurs photos de détail",
    type=[
        "jpg",
        "jpeg",
        "png",
    ],
    accept_multiple_files=True,
    key="details",
)


for i, file in enumerate(
    details,
    start=1,
):

    target = save_uploaded_photo(
        dossier_id,
        "details",
        file,
        index=i,
    )

    register_photo(
        dossier_id,
        "details",
        target,
    )


# ============================================================
# VÉRIFICATION DU DOSSIER
# ============================================================

metadata = load_metadata(dossier_id)

photos = metadata.get(
    "photos",
    [],
)


counts = {
    view: sum(
        p.get("view") == view
        for p in photos
    )
    for view in VIEWS
}


st.markdown(
    '<div class="cabek-section">Vérification du dossier</div>',
    unsafe_allow_html=True,
)


cols = st.columns(5)


for col, view in zip(
    cols,
    VIEWS,
):

    col.metric(
        VIEWS[view],
        counts[view],
    )


# ============================================================
# VÉRIFICATION DES 4 VUES
# ============================================================

required_ok = all(
    counts[v] >= 1
    for v in view_cols
)


if required_ok:

    st.success(
        "Les 4 vues principales sont présentes. "
        "Le dossier peut être envoyé à l'expertise IA."
    )

else:

    missing = ", ".join(
        VIEWS[v]
        for v in view_cols
        if counts[v] == 0
    )

    st.warning(
        f"Vues principales manquantes : {missing}"
    )


# ============================================================
# ENVOI À L'EXPERTISE IA
# ============================================================

if st.button(
    "📤 Envoyer le dossier à l'expertise IA",
    use_container_width=True,
    type="primary",
    disabled=not required_ok,
):

    set_status(
        dossier_id,
        "Envoyé",
    )

    st.success(
        "Dossier envoyé. "
        "Ouvre « Expertise IA » dans la barre latérale "
        "pour poursuivre."
    )