"""Built-in knowledge base and retrieval for QB GovLens.

The knowledge base is three curated markdown files in ``knowledge_base/``:
  GG  QB Admin Portal Governance Guide for Agencies (official, curated)
  DG  QB Admin Portal Data Glossary (official, field descriptions verbatim)
  RS  QB GovLens rule specification (tool documentation, NOT policy)

Each ``## [ID] Title`` section is one passage with a stable citation ID.

Retrieval uses OpenAI embeddings with a small local vector store (NumPy
matrix persisted to ``.cache/``), re-embedded only when the corpus or the
embedding model changes. Without an API key, or if embedding fails, a
deterministic keyword retriever is used and the UI says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
import re
from collections import Counter
from typing import Callable

import numpy as np

APP_DIR = Path(__file__).resolve().parents[1]
KB_DIR = APP_DIR / "knowledge_base"
CACHE_DIR = APP_DIR / ".cache"

DOC_LABELS = {
    "GG": "QB Admin Portal Governance Guide",
    "DG": "QB Admin Portal Data Glossary",
    "RS": "QB GovLens rule specification (tool documentation, not policy)",
}
DOC_ORDER = ("GG", "DG", "RS")
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
CITATION_RE = re.compile(r"\[((?:GG|DG|RS)-[A-Z0-9]+(?:-[A-Z0-9]+)*)\]")

EmbedFn = Callable[[list[str]], np.ndarray]


@dataclass(frozen=True)
class Passage:
    citation: str
    doc: str
    title: str
    page: str
    text: str

    @property
    def source(self) -> str:
        return DOC_LABELS.get(self.doc, self.doc)

    @property
    def location(self) -> str:
        if self.doc == "GG":
            return f"p.{self.page}"
        return self.page

    def embedding_text(self) -> str:
        return f"{self.source}. {self.title}.\n{self.text}"


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float
    method: str  # "embedding" or "keyword"


_HEADING = re.compile(r"^##\s+\[(?P<cid>[A-Z]{2}-[A-Z0-9-]+)\]\s+(?P<title>.+?)\s*$")


def parse_markdown(text: str) -> list[Passage]:
    """Parse ``## [ID] Title`` sections; an optional ``page:`` line follows the heading."""
    passages: list[Passage] = []
    current: dict | None = None

    def flush() -> None:
        if current is None:
            return
        body = "\n".join(current["lines"]).strip()
        if not body:
            raise ValueError(f"{current['cid']}: empty knowledge-base passage")
        passages.append(Passage(
            citation=current["cid"], doc=current["cid"][:2], title=current["title"],
            page=current["page"], text=body,
        ))

    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            current = {"cid": match["cid"], "title": match["title"], "page": "", "lines": []}
            continue
        if current is None:
            continue
        if not current["lines"] and not current["page"] and line.lower().startswith("page:"):
            current["page"] = line.split(":", 1)[1].strip()
            continue
        current["lines"].append(line)
    flush()
    return passages


def load_knowledge_base(kb_dir: Path = KB_DIR) -> list[Passage]:
    files = sorted(Path(kb_dir).glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No knowledge-base markdown files in {kb_dir}")
    passages = [p for f in files for p in parse_markdown(f.read_text(encoding="utf-8"))]
    ids = [p.citation for p in passages]
    duplicates = sorted({c for c in ids if ids.count(c) > 1})
    if duplicates:
        raise ValueError(f"Duplicate knowledge-base citation IDs: {duplicates}")
    return passages


def corpus_fingerprint(passages: list[Passage]) -> str:
    digest = sha256()
    for p in passages:
        digest.update(f"{p.citation}\x1f{p.embedding_text()}\x1e".encode("utf-8"))
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------- embeddings

def openai_embedder(api_key: str, model: str = DEFAULT_EMBEDDING_MODEL) -> EmbedFn:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=30, max_retries=2)

    def embed(texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        for start in range(0, len(texts), 96):
            response = client.embeddings.create(model=model, input=texts[start:start + 96])
            out.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return np.asarray(out, dtype=np.float32)

    return embed


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class VectorStore:
    """Cosine-similarity vector store over the knowledge-base passages."""

    def __init__(self, passages: list[Passage], vectors: np.ndarray, model: str):
        if len(passages) != len(vectors):
            raise ValueError("passages and vectors differ in length")
        self.passages = passages
        self.vectors = _normalise(np.asarray(vectors, dtype=np.float32))
        self.model = model

    @classmethod
    def build(cls, passages: list[Passage], embed: EmbedFn, model: str,
              cache_dir: Path | None = CACHE_DIR) -> "VectorStore":
        fingerprint = corpus_fingerprint(passages)
        safe_model = re.sub(r"[^A-Za-z0-9_.-]", "_", model)
        path = Path(cache_dir) / f"kb_vectors_{safe_model}_{fingerprint}.npz" if cache_dir else None
        if path and path.exists():
            data = np.load(path, allow_pickle=False)
            if list(data["citations"]) == [p.citation for p in passages]:
                return cls(passages, data["vectors"], model)
        vectors = embed([p.embedding_text() for p in passages])
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(path, vectors=vectors, citations=np.array([p.citation for p in passages]))
        return cls(passages, vectors, model)

    def search(self, query_vector: np.ndarray, k: int, docs: tuple[str, ...] | None = None) -> list[tuple[float, Passage]]:
        q = _normalise(np.asarray(query_vector, dtype=np.float32).reshape(1, -1))[0]
        scores = self.vectors @ q
        order = np.argsort(-scores, kind="stable")
        out = []
        for ix in order:
            p = self.passages[ix]
            if docs and p.doc not in docs:
                continue
            out.append((float(scores[ix]), p))
            if len(out) >= k:
                break
        return out


# ------------------------------------------------------------ keyword fallback

def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def keyword_search(passages: list[Passage], query: str, k: int,
                   docs: tuple[str, ...] | None = None) -> list[tuple[float, Passage]]:
    pool = [p for p in passages if not docs or p.doc in docs]
    if not pool:
        return []
    bags = [Counter(_tokens(p.embedding_text())) for p in pool]
    df = Counter(t for bag in bags for t in bag)
    n = len(bags)
    words = set(_tokens(query))
    scored = []
    for p, bag in zip(pool, bags):
        score = sum(
            min(bag[t], 3) * math.log(1 + (n + 1) / (1 + df[t]))
            for t in words if t in bag
        )
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], x[1].citation))
    return scored[:k]


# ------------------------------------------------------------------ retriever

class Retriever:
    """Embedding retriever with an explicit, labelled keyword fallback."""

    def __init__(self, passages: list[Passage], store: VectorStore | None = None,
                 embed: EmbedFn | None = None, note: str = ""):
        self.passages = passages
        self.store = store
        self.embed = embed
        self.note = note

    @property
    def method(self) -> str:
        return "embedding" if self.store is not None and self.embed is not None else "keyword"

    @property
    def description(self) -> str:
        if self.method == "embedding":
            return f"Embedding similarity ({self.store.model}, local vector store, {len(self.passages)} passages)"
        return "Keyword retrieval fallback (no embeddings)" + (f": {self.note}" if self.note else "")

    def search(self, query: str, per_doc: dict[str, int]) -> list[Hit]:
        return self.search_many([query], per_doc)[0]

    def search_many(self, queries: list[str], per_doc: dict[str, int]) -> list[list[Hit]]:
        """Search several queries, embedding them in one batch call."""
        vectors = None
        if self.method == "embedding" and queries:
            try:
                vectors = self.embed(list(queries))
            except Exception as exc:  # network/key issues: degrade these queries, do not crash
                self.note = f"query embedding failed ({type(exc).__name__}); keyword fallback used"
                vectors = None
        return [
            self._search_one(q, vectors[i] if vectors is not None else None, per_doc)
            for i, q in enumerate(queries)
        ]

    def _search_one(self, query: str, query_vector, per_doc: dict[str, int]) -> list[Hit]:
        hits: list[Hit] = []
        for doc in DOC_ORDER:
            k = per_doc.get(doc, 0)
            if not k:
                continue
            if query_vector is not None:
                found = self.store.search(query_vector, k, docs=(doc,))
                hits.extend(Hit(p, s, "embedding") for s, p in found)
            else:
                found = keyword_search(self.passages, query, k, docs=(doc,))
                hits.extend(Hit(p, s, "keyword") for s, p in found)
        return hits


def build_retriever(api_key: str = "", model: str = DEFAULT_EMBEDDING_MODEL,
                    kb_dir: Path = KB_DIR, cache_dir: Path | None = CACHE_DIR,
                    embed: EmbedFn | None = None) -> Retriever:
    passages = load_knowledge_base(kb_dir)
    if embed is None and api_key:
        embed = openai_embedder(api_key, model)
    if embed is None:
        return Retriever(passages, note="no OpenAI API key set")
    try:
        store = VectorStore.build(passages, embed, model, cache_dir)
    except Exception as exc:
        return Retriever(passages, note=f"embedding the knowledge base failed ({type(exc).__name__}: {exc})"[:300])
    return Retriever(passages, store, embed)
