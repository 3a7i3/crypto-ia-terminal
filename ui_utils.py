"""
Module utilitaire pour automatiser les patterns UI (Streamlit/Plotly) :
- Export PNG/SVG/QR
- Gestion fallback data/erreur
- Intégration tutoriel/FAQ
- Contrôles caméra Plotly
- Sidebar/menu/navigation
"""

import base64
import io

import plotly.io as pio
import streamlit as st

try:
    import qrcode
except ImportError:
    qrcode = None


def export_plotly_png(fig, filename="plot.png"):
    img_bytes = pio.to_image(fig, format="png")
    st.download_button(
        "Exporter la vue (PNG)", data=img_bytes, file_name=filename, mime="image/png"
    )


def export_plotly_svg(fig, filename="plot.svg"):
    img_bytes = pio.to_image(fig, format="svg")
    st.download_button(
        "Exporter la vue (SVG)",
        data=img_bytes,
        file_name=filename,
        mime="image/svg+xml",
    )


def export_qr_code(data, label="Partager la vue (QR)"):
    if not qrcode:
        st.warning("qrcode non installé")
        return
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf)
    buf.seek(0)
    st.image(buf, caption=label)
    b64 = base64.b64encode(buf.getvalue()).decode()
    href = f'<a href="data:image/png;base64,{b64}" download="qr.png">Télécharger QR</a>'
    st.markdown(href, unsafe_allow_html=True)


def show_fallback(message="Aucune donnée disponible. Veuillez lancer la simulation."):
    st.warning(message)


def show_tutorial(tuto_md_path="TUTORIEL_EVOLUTION_DASHBOARD_FR.md"):
    try:
        with open(tuto_md_path, encoding="utf-8") as f:
            st.markdown(f.read())
    except Exception:
        st.info("Tutoriel non disponible.")


def show_faq(faq_md_path="FAQ_EVOLUTION_DASHBOARD_FR.md"):
    try:
        with open(faq_md_path, encoding="utf-8") as f:
            st.markdown(f.read())
    except Exception:
        st.info("FAQ non disponible.")


def sidebar_navigation(panels):
    st.sidebar.title("Navigation")
    return st.sidebar.radio("Aller vers :", panels)
