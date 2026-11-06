"""The agent crew, run offline with a scripted LLM (no API key, no network).

The scripted model answers in CrewAI's text format (Thought / Action / Final Answer), so
CrewAI really parses its tool calls, runs the GovLens tools, injects the skills into the
prompts, and applies the citation guardrail. Only the language model is fake.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("crewai")

from crewai.llms.base_llm import BaseLLM  # noqa: E402

from govlens import crew  # noqa: E402
from govlens.demo import load_masked_sample  # noqa: E402
from govlens.engine import analyse  # noqa: E402
from govlens.knowledge import build_retriever  # noqa: E402
from govlens.rag import retrieve  # noqa: E402

CASES, ORDERS, DETAIL, _ = analyse(*load_masked_sample())
RETRIEVER = build_retriever(api_key="")  # keyword retrieval, offline
G2C = CASES[CASES["Case_ID"] == "GL-BBB432A3D3F7"].iloc[0]
FIRST_ORDER = str(G2C["Evidence_Order_IDs"]).split("|")[0].strip()


def act(tool: str, args: dict[str, Any]) -> str:
    return f"Thought: I need data.\nAction: {tool}\nAction Input: {json.dumps(args)}"


def final(text: str) -> str:
    return f"Thought: I now know the final answer\nFinal Answer: {text}"


REPORT = (
    "**Signal**\nFive buyers bought Food & Beverages in one half-year.\n\n"
    f"**Transaction evidence**\nOne buyer placed 10 orders with one seller on 10 Mar 2026 [QB:{FIRST_ORDER}].\n\n"
    "**Relevant guidance**\nThe guide suggests checking buyers in one department buying the same category "
    "[GG-CHECK-SPLIT].\n\n**Possible legitimate explanations**\nSellers can limit quantity per cart "
    "[GG-CHECK-SPLIT].\n\n**Checks for the administrator**\nAsk each team for its pantry plan.\n\n"
    "This is a review list item, not a finding."
)


class ScriptedLLM(BaseLLM):
    """Plays each agent's part from a script keyed by the agent's role."""

    model: str = "scripted"
    prompts: dict = {}
    writer_attempts: int = 0

    def call(self, messages, tools=None, callbacks=None, available_functions=None,
             from_task=None, from_agent=None, response_model=None):
        role = getattr(from_agent, "role", "")
        text = json.dumps(messages) if not isinstance(messages, str) else messages
        self.prompts.setdefault(role, text)
        step = text.count("Observation:") - text.count("Observation: the result")  # tool results so far
        if role == "Evidence analyst":
            script = [act("case_overview", {}), act("summarise_orders", {"group_by": ["date", "seller"]}),
                      final(f"Supports a single need: 10 orders on one day [QB:{FIRST_ORDER}].")]
        elif role == "Guidance researcher":
            script = [act("search_guidance", {"query": "seller limits quantity per cart"}),
                      final("[GG-CHECK-SPLIT] bears on the same-day orders; it names seller cart limits.")]
        elif role == "Report writer":
            self.writer_attempts += 1
            # First attempt cites a passage nobody retrieved; the guardrail must send it back.
            return final(REPORT.replace("[GG-CHECK-SPLIT].\n\n**Possible", "[GG-MADE-UP].\n\n**Possible")
                         if self.writer_attempts == 1 else REPORT)
        else:  # Case Q&A assistant
            script = [act("summarise_orders", {"group_by": ["buyer"]}),
                      final(f"Buyer A placed the most orders, e.g. [QB:{FIRST_ORDER}].")]
        return script[min(step, len(script) - 1)]

    def supports_stop_words(self) -> bool:
        return True

    def get_context_window_size(self) -> int:
        return 128_000


def test_review_crew_runs_tools_applies_skills_and_guardrail():
    llm = ScriptedLLM(model="scripted")
    log: list[str] = []
    result = crew.review_case(G2C, ORDERS, DETAIL, RETRIEVER, api_key="", model="scripted",
                              baseline_hits=retrieve(RETRIEVER, G2C), progress=log.append, llm=llm)
    assert result.text.startswith("**Signal**")
    assert [p.citation for p in result.passages] == ["GG-CHECK-SPLIT"]
    assert [c["tool"] for c in result.tool_calls] == ["case_overview", "summarise_orders", "search_guidance"]
    assert llm.writer_attempts == 2, "the citation guardrail should have sent the first draft back"
    assert any(line.startswith("Tool: summarise_orders") for line in log)
    # Skills reach the prompts: each agent's own skill plus the crew-level citation skill.
    assert "Analysing the evidence behind a split-purchase case" in llm.prompts["Evidence analyst"]
    assert "Finding the guidance that applies to this case" in llm.prompts["Guidance researcher"]
    assert "Writing the case review report" in llm.prompts["Report writer"]
    assert all("Citing sources in QB GovLens" in p for p in llm.prompts.values())
    # Buyer e-mails never reach the model.
    assert "@" not in "".join(llm.prompts.values()).replace("@org", "")


def test_follow_up_question_uses_tools_and_needs_no_passage():
    llm = ScriptedLLM(model="scripted")
    result = crew.answer_question("Who placed the most orders?", G2C, ORDERS, DETAIL, RETRIEVER,
                                  api_key="", model="scripted", llm=llm)
    assert result.text.startswith("Buyer A")
    assert [c["tool"] for c in result.tool_calls] == ["summarise_orders"]


def test_crew_answer_is_rejected_when_citations_cannot_be_fixed():
    class AlwaysWrong(ScriptedLLM):
        def call(self, messages, **kwargs):
            if getattr(kwargs.get("from_agent"), "role", "") == "Case Q&A assistant":
                return final("See [GG-NOT-A-PASSAGE] and [QB:999999].")
            return super().call(messages, **kwargs)

    with pytest.raises(Exception):
        crew.answer_question("What does the guide say?", G2C, ORDERS, DETAIL, RETRIEVER,
                             api_key="", model="scripted", llm=AlwaysWrong(model="scripted"))


def test_check_citations():
    ok = crew.check_citations(f"x [GG-CHECK-SPLIT] [QB:{FIRST_ORDER}]", {"GG-CHECK-SPLIT"}, {FIRST_ORDER})
    assert ok == []
    problems = crew.check_citations("x [GG-OTHER] [QB:1, 2]", {"GG-CHECK-SPLIT"}, {"1"})
    assert any("GG-OTHER" in p for p in problems) and any("'2'" in p for p in problems)
    assert crew.check_citations("no refs", set(), set(), require_passage=False) == []
    assert crew.check_citations("no refs", set(), set()) == ["it cites no knowledge-base passage"]
