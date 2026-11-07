"""Evaluation helpers and the skill files."""

from __future__ import annotations

import pandas as pd

from govlens import evaluation as ev
from govlens import justification as js
from govlens.skills import list_skills, read_skill


def test_untraceable_amounts_flags_only_numbers_missing_from_the_sources():
    sources = ['{"total": 27701.06, "buyers": [{"total": 5988.3}]}', "Evidence: $4,796.22 before"]
    text = "Total $27,701.06; Buyer A $5,988; before the reset $4,796.22; limit $6,000; made up $1,234.50."
    assert ev.untraceable_amounts(text, sources) == [1234.5]
    assert ev.amounts_in("no money here") == []


def test_blind_order_is_stable_and_uses_both_engines():
    first = ev.blind_order(["c1", "c2", "c3"])
    assert first == ev.blind_order(["c1", "c2", "c3"])
    assert all(sorted(v) == ["crew", "single"] for v in first.values())


def test_agreement_counts_direction_of_disagreement():
    labels = pd.DataFrame({
        "your_tier": ["High", "Medium", "Low", "Low", ""],
        "govlens_tier": ["High", "High", "Medium", "Low", "Medium"],
    })
    result = ev.agreement(labels)
    assert result["labelled"] == 4
    assert result["exact_agreement"] == 0.5
    assert result["govlens_higher"] == 2 and result["govlens_lower"] == 0
    assert result["confusion"]["Medium"]["High"] == 1


def test_skills_are_valid_and_the_justification_skill_matches_the_prompt_version():
    skills = {s.name: s for s in list_skills()}
    assert set(skills) == {
        "govlens-case-qa", "govlens-case-report", "govlens-citations", "govlens-evidence-analysis",
        "govlens-guidance-research", "govlens-purchase-justification",
    }
    assert all(s.description and s.body and s.version for s in skills.values())
    # The app sends the skill body as the system prompt; its version tag must match, because
    # the version is part of the cache key that decides which shipped AI results are valid.
    skill = read_skill("govlens-purchase-justification")
    assert js.SYSTEM_PROMPT == skill.body
    assert skill.metadata["prompt-version"] == js.PROMPT_VERSION
