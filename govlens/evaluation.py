"""Evaluation helpers: automatic checks on AI text, and agreement with a human reviewer's labels.

Two evaluations, both run locally with scripts/ and saved under evaluation/ so the
Methodology page can show the results without any API calls:

* Case reviews (use case 1): the crew and the single-call explanation are run on every
  G2B/G2C case in the masked sample. Automatic checks: did the answer pass the citation
  check, how long it took, and how many dollar figures in the text cannot be traced to the
  data the model was given (a proxy for invented numbers). The reports are also written
  out as "Report A / Report B" in random order, so a reviewer can rate them blind.
* Purchase justification (use case 2): a reviewer gives their own tier for a stratified
  sample of carts without seeing GovLens's tier; agreement is then computed.
"""

from __future__ import annotations

from pathlib import Path
import random
import re

import pandas as pd

from .knowledge import APP_DIR

EVAL_DIR = APP_DIR / "evaluation"
REVIEW_RUNS = EVAL_DIR / "review_runs.csv"
REVIEW_LABELS = EVAL_DIR / "review_labels.csv"
REVIEW_REPORTS = EVAL_DIR / "review_reports.md"
JUSTIFICATION_LABELS = EVAL_DIR / "justification_labels.csv"
TIERS = ["High", "Medium", "Low"]

_AMOUNT = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def amounts_in(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in _AMOUNT.findall(text or "")]


def untraceable_amounts(text: str, sources: list[str], constants: tuple[float, ...] = (6000.0,)) -> list[float]:
    """Dollar figures in ``text`` that match no number in ``sources`` (to the cent or the dollar)."""
    known = set(constants)
    for source in sources:
        known.update(float(n) for n in _NUMBER.findall((source or "").replace(",", "")))
    cents = {round(k, 2) for k in known}
    dollars = {round(k) for k in known}
    return [a for a in amounts_in(text) if round(a, 2) not in cents and round(a) not in dollars]


def blind_order(case_ids: list[str], seed: int = 7) -> dict[str, list[str]]:
    """Per case, the order in which the two engines are shown as Report A and Report B."""
    rng = random.Random(seed)
    out = {}
    for case_id in case_ids:
        engines = ["crew", "single"]
        rng.shuffle(engines)
        out[case_id] = engines
    return out


def stratified_carts(table: pd.DataFrame, per_group: dict[str, int] | None = None, seed: int = 11) -> pd.DataFrame:
    """A small labelling sample across tiers and reason types (deterministic).

    ``table`` needs Cart_ID, Tier and Rule_Vague columns (from combined_tier).
    """
    per_group = per_group or {"High": 4, "Medium (vague reason)": 3, "Medium (stated reason)": 3, "Low": 2}
    t = table.copy()
    same = [c for c in ("Reason_For_Purchase", "Cart_Item_Total") if c in t.columns]
    if same:  # identical carts (e.g. many 'QB2025' carts for the same item) would waste labels
        t = t.drop_duplicates(subset=same)
    t["Group"] = t["Tier"]
    medium = t["Tier"] == "Medium"
    t.loc[medium & t["Rule_Vague"], "Group"] = "Medium (vague reason)"
    t.loc[medium & ~t["Rule_Vague"], "Group"] = "Medium (stated reason)"
    picks = [
        t[t["Group"] == group].sample(n=min(n, int((t["Group"] == group).sum())), random_state=seed)
        for group, n in per_group.items()
    ]
    return pd.concat(picks).sample(frac=1, random_state=seed).reset_index(drop=True)


def agreement(labels: pd.DataFrame) -> dict:
    """Agreement between the reviewer's tier and GovLens's tier (rows with a label only)."""
    done = labels[labels["your_tier"].isin(TIERS)].copy()
    if done.empty:
        return {"labelled": 0}
    exact = (done["your_tier"] == done["govlens_tier"]).mean()
    rank = {t: i for i, t in enumerate(TIERS)}
    gap = (done["govlens_tier"].map(rank) - done["your_tier"].map(rank))
    confusion = pd.crosstab(done["your_tier"], done["govlens_tier"]).reindex(index=TIERS, columns=TIERS, fill_value=0)
    return {
        "labelled": int(len(done)),
        "exact_agreement": round(float(exact), 3),
        "govlens_higher": int((gap < 0).sum()),   # GovLens more cautious than the reviewer
        "govlens_lower": int((gap > 0).sum()),
        "confusion": {r: {c: int(confusion.loc[r, c]) for c in TIERS} for r in TIERS},
    }


def read_csv(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return None
