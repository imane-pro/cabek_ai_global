import streamlit as st
from PIL import Image
from core.ui import header
from core.dossier_manager import VIEWS, create_dossier, load_metadata, save_uploaded_photo, register_photo, set_status

header("Collecte des données", "Création d’un dossier photo pour expertise IA")

if "dossier_id" not in st.session_state:
    st.session_state.dossier_id = None

with st.form("vehicle_form"):
    st.markdown('<div class="cabek-section">1 · Informations du véhicule</div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns(3)
    with c1:
        marque = st.text_input("Marque *", placeholder="Ex. Toyota")
        modele = st.text_input("Modèle", placeholder="Ex. Corolla")
    with c2:
        matricule = st.text_input("Matricule *", placeholder="Ex. 12345-A-6")
        expert = st.text_input("Expert / agent", placeholder="Nom ou matricule")
    with c3:
        annee = st.text_input("Année", placeholder="Ex. 2020")
        type_vehicule = st.selectbox("Type de véhicule", ["Particulier","Utilitaire","Moto","Autre"])
    start = st.form_submit_button("Créer le dossier", use_container_width=True, type="primary")

if start:
    if not marque.strip() or not matricule.strip():
        st.error("La marque et le matricule sont obligatoires.")
    else:
        st.session_state.dossier_id = create_dossier(marque, matricule, modele, expert)
        st.success(f"Dossier créé : {st.session_state.dossier_id}")

if not st.session_state.dossier_id:
    st.info("Crée d’abord le dossier véhicule, puis ajoute les photos guidées.")
    st.stop()

dossier_id = st.session_state.dossier_id
metadata = load_metadata(dossier_id)

st.markdown('<div class="cabek-section">2 · Photos du véhicule</div>', unsafe_allow_html=True)
st.caption(f"Dossier {dossier_id} · {metadata['marque']} {metadata.get('modele','')} · Matricule {metadata['matricule']}")

view_cols = ["avant","arriere","gauche","droite"]
for view in view_cols:
    st.markdown(f"#### {VIEWS[view]}")
    c1,c2 = st.columns([1,1])
    with c1:
        camera = st.camera_input(f"Prendre {VIEWS[view]}", key=f"cam_{view}")
    with c2:
        upload = st.file_uploader(f"Importer — {VIEWS[view]}", type=["jpg","jpeg","png"], key=f"up_{view}")
    selected = camera or upload
    if selected is not None:
        target = save_uploaded_photo(dossier_id, view, selected, index=1)
        register_photo(dossier_id, view, target)
        st.image(Image.open(target), caption=VIEWS[view], width=420)

st.markdown('<div class="cabek-section">3 · Détails des dommages</div>', unsafe_allow_html=True)
details = st.file_uploader("Ajouter une ou plusieurs photos de détail", type=["jpg","jpeg","png"], accept_multiple_files=True, key="details")
for i,f in enumerate(details,start=1):
    target = save_uploaded_photo(dossier_id,"details",f,index=i)
    register_photo(dossier_id,"details",target)

metadata = load_metadata(dossier_id)
photos = metadata.get("photos",[])
counts = {v: sum(p.get("view")==v for p in photos) for v in VIEWS}

st.markdown('<div class="cabek-section">Vérification du dossier</div>', unsafe_allow_html=True)
cols = st.columns(5)
for col,view in zip(cols,VIEWS): col.metric(VIEWS[view],counts[view])
required_ok = all(counts[v] >= 1 for v in view_cols)

if required_ok:
    st.success("Les 4 vues principales sont présentes. Le dossier peut être envoyé à l’expertise IA.")
else:
    missing = ", ".join(VIEWS[v] for v in view_cols if counts[v]==0)
    st.warning(f"Vues principales manquantes : {missing}")

if st.button("📤 Envoyer le dossier à l’expertise IA", use_container_width=True, type="primary", disabled=not required_ok):
    set_status(dossier_id,"Envoyé")
    st.success("Dossier envoyé. Ouvre « Expertise IA » dans la barre latérale pour poursuivre.")
