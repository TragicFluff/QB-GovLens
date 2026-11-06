"""QB GovLens: entry point. Sign-in gate, then a three-page app.

Start with: streamlit run app.py
Pages (views/): Governance review (main page, both use cases), About Us, Methodology.
Uses masked/desensitised data only; this is an educational prototype.
"""

from __future__ import annotations

import streamlit as st

from govlens.auth import login_gate

st.set_page_config(page_title="QB GovLens | Agency Admin", page_icon="🔎", layout="wide")

if not login_gate(st):
    st.stop()

pages = [
    st.Page("views/review.py", title="Governance review", icon="🔎", default=True),
    st.Page("views/about.py", title="About Us", icon="ℹ️"),
    st.Page("views/methodology.py", title="Methodology", icon="🧭"),
]
navigation = st.navigation(pages)

with st.sidebar:
    if st.button("Sign out", key="sign_out"):
        st.session_state.clear()
        st.rerun()

navigation.run()
