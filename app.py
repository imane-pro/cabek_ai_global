import streamlit as st
from core.ui import inject_css, sidebar_brand

st.set_page_config(
    page_title="CABEK.AI — Expertise automobile",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

accueil = st.Page(
    "pages/1_Accueil.py",
    title="Accueil",
    icon="🏠"
)

collecte = st.Page(
    "pages/2_Collecte.py",
    title="Collecte des données",
    icon="📷"
)

expertise = st.Page(
    "pages/3_Expertise_IA.py",
    title="Expertise IA",
    icon="🤖"
)

sidebar_brand()

pg = st.navigation(
    [accueil, collecte, expertise],
    position="sidebar"
)

st.sidebar.markdown("---")
st.sidebar.caption("CABEK.AI · Application globale")
st.sidebar.caption("Collecte → Expertise → Validation")

pg.run()