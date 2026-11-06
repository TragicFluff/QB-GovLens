"""Streamlit helpers shared by the pages: models, API key, retriever and display helpers."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

import streamlit as st

from .config import get_api_key
from .knowledge import build_retriever, corpus_fingerprint, load_knowledge_base
from . import models

CHAT_MODEL = models.CHAT_MODEL
EMBEDDING_MODEL = models.EMBEDDING_MODEL


def _secret(name: str) -> str:
    return st.secrets[name]


def api_key() -> str:
    return get_api_key(_secret)


@st.cache_resource(show_spinner="Preparing the knowledge base...")
def _cached_retriever(key_fingerprint: str, embed_model: str, corpus_fp: str, _api_key: str):
    return build_retriever(_api_key, embed_model)


def retriever(key: str):
    kb_fp = corpus_fingerprint(load_knowledge_base())
    key_fp = sha256(key.encode()).hexdigest()[:12] if key else "none"
    return _cached_retriever(key_fp, EMBEDDING_MODEL, kb_fp, key), kb_fp


@st.cache_data(show_spinner=False)
def related_guidance(_retriever, cache_token: str, query: str, per_doc: tuple[tuple[str, int], ...]):
    return _retriever.search(query, dict(per_doc))


def md(text) -> str:
    """Escape $ so currency amounts are not rendered as LaTeX by st.markdown."""
    return str(text).replace("$", "\\$")


def show_hits(hits) -> None:
    for h in hits:
        p = h.passage
        score = f"similarity {h.score:.2f}" if h.method == "embedding" else f"keyword score {h.score:.1f}"
        st.markdown(f"**[{p.citation}] {p.title}**  \n*{p.source}, {p.location} · {score}*")
        st.markdown(md(p.text))


def now_sgt() -> datetime:
    return datetime.now(ZoneInfo("Asia/Singapore"))


def reviewer_notes(key: str, payload: dict, file_stem: str) -> None:
    """Disposition, notes and a JSON download of the reviewer's record (browser session only)."""
    st.markdown("**Human reviewer notes (browser session only)**")
    disposition = st.selectbox(
        "Preliminary disposition",
        ["Pending contextual review", "No further action after review", "Further verification required"],
        key=f"disp-{key}",
    )
    notes = st.text_area(
        "Document business context and action required", key=f"notes-{key}",
        placeholder="E.g. Verify purchasing need, approvals and seller details.",
    )
    record = {
        **payload,
        "disposition": disposition,
        "reviewer_notes": notes,
        "recorded_at_sgt": now_sgt().isoformat(timespec="seconds"),
        "limitation": "Human review required; no production authorisation/audit persistence.",
    }
    st.download_button(
        "Download this review (JSON)",
        json.dumps(record, indent=2, ensure_ascii=False, default=str).encode("utf-8"),
        file_name=f"{file_stem}.json", mime="application/json", key=f"dl-{key}",
    )


def status_writer(status):
    """Progress callback that writes into an st.status box, ignoring calls it cannot render."""
    def write(message: str) -> None:
        try:
            status.write(message)
        except Exception:  # e.g. called from a worker thread without a Streamlit context
            pass
    return write
