import streamlit as st


def inject_css():
    st.markdown("""
    <style>
    :root{
      --cabek-blue:#1769FF;
      --cabek-blue-2:#0E56D8;
      --cabek-navy:#0D2344;
      --cabek-bg:#F4F7FB;
      --cabek-panel:#FFFFFF;
      --cabek-line:#E3EAF3;
      --cabek-text:#172033;
      --cabek-muted:#718096;
      --cabek-green:#12A875;
      --cabek-red:#E84B4B;
      --cabek-orange:#D99016;
    }
    .stApp{background:var(--cabek-bg);color:var(--cabek-text)}
    [data-testid="stHeader"]{background:transparent}
    [data-testid="stSidebar"]{background:linear-gradient(180deg,#092044 0%,#0E2A50 100%);border-right:1px solid #17365F}
    [data-testid="stSidebar"] *{color:#EAF2FF !important}
    [data-testid="stSidebar"] .stButton button{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)}
    [data-testid="stSidebar"] .stCaption{color:#AFC1DC !important}
    .block-container{max-width:1500px;padding-top:1.15rem;padding-bottom:2rem}
    .cabek-topbar{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:14px}
    .cabek-brand{font-size:2rem;font-weight:850;letter-spacing:-.03em;color:var(--cabek-navy)}
    .cabek-brand span{color:var(--cabek-blue)}
    .cabek-sub{color:var(--cabek-muted);font-size:.88rem;margin-top:-6px}
    .cabek-hero{background:linear-gradient(135deg,#0D2344,#1558C8);color:white;border-radius:18px;padding:22px 24px;margin:4px 0 18px;box-shadow:0 8px 28px rgba(20,70,140,.12)}
    .cabek-hero h1{margin:0;font-size:1.7rem;color:white}.cabek-hero p{margin:5px 0 0;color:#DCE9FF}
    .cabek-card{background:var(--cabek-panel);border:1px solid var(--cabek-line);border-radius:14px;padding:16px 18px;margin-bottom:12px;box-shadow:0 2px 8px rgba(19,45,80,.03)}
    .cabek-card-title{font-weight:750;font-size:1rem;margin-bottom:4px}.cabek-muted{color:var(--cabek-muted)}
    .cabek-kpi{font-size:1.65rem;font-weight:800;line-height:1.1}.cabek-label{font-size:.7rem;color:var(--cabek-muted);text-transform:uppercase;letter-spacing:.06em;margin-top:5px}
    .cabek-section{font-size:1.05rem;font-weight:800;margin:18px 0 10px;color:var(--cabek-navy)}
    .cabek-pill{display:inline-block;border-radius:999px;padding:5px 10px;font-size:.72rem;font-weight:750}
    .pill-blue{background:#EAF2FF;color:#1558C8}.pill-green{background:#E8F8F1;color:#087E59}.pill-orange{background:#FFF5DF;color:#A96B00}.pill-red{background:#FDECEC;color:#C83232}
    .stButton button{border-radius:10px;font-weight:700}
    .stDownloadButton button{border-radius:10px;font-weight:700}
    div[data-testid="stMetric"]{background:white;border:1px solid var(--cabek-line);border-radius:14px;padding:10px 14px}
    </style>
    """, unsafe_allow_html=True)


def header(title, subtitle=""):
    st.markdown(
        f'<div class="cabek-topbar"><div><div class="cabek-brand">CABEK<span>.AI</span></div>'
        f'<div class="cabek-sub">{subtitle}</div></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="cabek-hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def sidebar_brand():
    st.sidebar.markdown(
        '<div style="padding:6px 4px 18px"><div style="font-size:1.55rem;font-weight:850;letter-spacing:-.03em">CABEK<span style="color:#54A0FF">.AI</span></div><div style="font-size:.72rem;color:#AFC1DC !important">Expertise automobile</div></div>',
        unsafe_allow_html=True,
    )
