"""Run both explanation engines on every G2B/G2C case in the masked sample and save the results.

Usage (from the project folder, with OPENAI_API_KEY in .env):
    python scripts/evaluate_reviews.py

Writes, under evaluation/:
  review_runs.csv     one row per case and engine: passed the citation check, seconds, tokens,
                      tool calls, dollar figures that cannot be traced to the model's input
  review_reports.md   both reports per case as "Report A" and "Report B" in random order
  review_labels.csv   a blank form for rating the reports blind (kept if already filled in)

Cost: roughly 8 cases x (1 + about 8) gpt-4o-mini calls, a few US cents in total.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import pandas as pd  # noqa: E402

from govlens import crew  # noqa: E402
from govlens import evaluation as ev  # noqa: E402
from govlens.config import get_api_key  # noqa: E402
from govlens.demo import load_masked_sample  # noqa: E402
from govlens.engine import analyse  # noqa: E402
from govlens.knowledge import build_retriever  # noqa: E402
from govlens.models import CHAT_MODEL  # noqa: E402
from govlens.rag import build_payload, openai_explanation, retrieve  # noqa: E402


def main() -> int:
    api_key = get_api_key()
    if not api_key:
        print("Set OPENAI_API_KEY (in .env or the environment) first.")
        return 1
    if not crew.available():
        print("CrewAI is not installed: pip install -r requirements.txt")
        return 1
    cases, orders, detail, _ = analyse(*load_masked_sample())
    cases = cases[cases["Rule_ID"].isin(["G2B", "G2C"])]
    retriever = build_retriever(api_key=api_key)
    order = ev.blind_order(cases["Case_ID"].tolist())
    runs, reports = [], []
    for _, case in cases.iterrows():
        case_id = case["Case_ID"]
        hits = retrieve(retriever, case)
        texts = {}
        print(f"{case_id} ({case['Rule_ID']})")
        # Crew
        started = time.time()
        try:
            run = crew.review_case(case, orders, detail, retriever, api_key, CHAT_MODEL, baseline_hits=hits)
            texts["crew"] = run.text
            sources = run.tool_outputs + [json.dumps({k: str(v) for k, v in case.items()})]
            runs.append({"case_id": case_id, "rule": case["Rule_ID"], "engine": "crew", "passed": True,
                         "seconds": run.seconds, "total_tokens": run.tokens.get("total_tokens", ""),
                         "llm_requests": run.tokens.get("successful_requests", ""), "tool_calls": len(run.tool_calls),
                         "untraceable_amounts": len(ev.untraceable_amounts(run.text, sources)),
                         "amounts_in_text": len(ev.amounts_in(run.text)), "error": ""})
        except Exception as exc:
            texts["crew"] = f"(no verified report: {exc})"
            runs.append({"case_id": case_id, "rule": case["Rule_ID"], "engine": "crew", "passed": False,
                         "seconds": round(time.time() - started, 1), "error": str(exc)[:300]})
        # Single call
        started = time.time()
        passages = [h.passage for h in hits]
        try:
            text = openai_explanation(case, orders, detail, passages, api_key, model=CHAT_MODEL)
            texts["single"] = text
            payload = json.dumps(build_payload(case, orders, detail, passages), default=str)
            runs.append({"case_id": case_id, "rule": case["Rule_ID"], "engine": "single", "passed": True,
                         "seconds": round(time.time() - started, 1), "llm_requests": 1, "tool_calls": 0,
                         "untraceable_amounts": len(ev.untraceable_amounts(text, [payload])),
                         "amounts_in_text": len(ev.amounts_in(text)), "error": ""})
        except Exception as exc:
            texts["single"] = f"(no verified report: {exc})"
            runs.append({"case_id": case_id, "rule": case["Rule_ID"], "engine": "single", "passed": False,
                         "seconds": round(time.time() - started, 1), "error": str(exc)[:300]})
        a, b = order[case_id]
        for label, engine in (("A", a), ("B", b)):
            runs[-2 if engine == "crew" else -1]["blind_label"] = label
        reports.append(f"## {case_id} ({case['Rule_ID']}, {case['Risk_Tier']})\n\n{case['Evidence_Summary']}\n\n"
                       f"### Report A\n\n{texts[a]}\n\n### Report B\n\n{texts[b]}\n")

    ev.EVAL_DIR.mkdir(exist_ok=True)
    pd.DataFrame(runs).to_csv(ev.REVIEW_RUNS, index=False)
    ev.REVIEW_REPORTS.write_text("# Case review reports for blind rating\n\n" + "\n".join(reports), encoding="utf-8")
    labels = ev.read_csv(ev.REVIEW_LABELS)
    if labels is None or not (labels.drop(columns=["case_id", "report"], errors="ignore") != "").any().any():
        pd.DataFrame([
            {"case_id": c, "report": r, "facts_correct_Y_N": "", "useful_1_to_5": "", "note": ""}
            for c in cases["Case_ID"] for r in ("A", "B")
        ]).to_csv(ev.REVIEW_LABELS, index=False, encoding="utf-8-sig")
    print(pd.DataFrame(runs).groupby("engine")[["passed", "seconds", "untraceable_amounts"]]
          .agg(lambda s: pd.to_numeric(s, errors="coerce").mean()).round(2))
    print(f"Saved {ev.REVIEW_RUNS.relative_to(APP_DIR)}, {ev.REVIEW_REPORTS.relative_to(APP_DIR)} and "
          f"{ev.REVIEW_LABELS.relative_to(APP_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
