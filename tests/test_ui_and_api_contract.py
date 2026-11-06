"""Mocked integration tests: pages run end to end with a Streamlit stub; OpenAI calls are faked."""

import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import govlens.auth
import govlens.config
from govlens import justification as js
from govlens.flowcharts import FLOWCHARTS
from govlens.demo import create_demo
from govlens.engine import analyse
from govlens.knowledge import build_retriever
from govlens.rag import openai_explanation, retrieve


class Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def metric(self, *args, **kwargs):
        pass

    def multiselect(self, label, options, default=None, **kwargs):
        return default


def _cache_decorator(*args, **kwargs):
    if args and callable(args[0]):
        return args[0]
    return lambda fn: fn


class Secrets:
    def __getitem__(self, key):
        raise KeyError(key)


def fake_streamlit(review_button=True):
    module = ModuleType("streamlit")
    module.sidebar = Ctx()
    module.session_state = {}
    module.secrets = Secrets()
    module.cache_resource = _cache_decorator
    module.cache_data = _cache_decorator
    call_counts = {"review": 0, "radio": [], "number_input": [], "slider": [], "dataframes": [], "tabs": []}

    def noop(*args, **kwargs):
        return None

    for fn in [
        "set_page_config", "title", "caption", "warning", "header", "divider",
        "info", "error", "markdown", "write", "code", "subheader",
        "text", "download_button", "json", "graphviz_chart",
    ]:
        setattr(module, fn, noop)
    module.dataframe = lambda data, *a, **k: call_counts["dataframes"].append(data)
    module.form = lambda *a, **k: Ctx()
    module.form_submit_button = lambda *a, **k: False
    module.rerun = noop
    navigation = {"pages": None, "ran": False}

    class Page:
        def __init__(self, path, **kwargs):
            self.path, self.kwargs = path, kwargs

    def navigate(pages, **kwargs):
        navigation["pages"] = pages
        return SimpleNamespace(run=lambda: navigation.update(ran=True))

    module.Page = Page
    module.navigation = navigate
    module.navigation_state = navigation
    module.stop = lambda: (_ for _ in ()).throw(SystemExit("st.stop"))
    module.progress = lambda *a, **k: SimpleNamespace(progress=noop)
    module.radio = lambda label, opts, **kwargs: call_counts["radio"].extend(opts) or opts[0]
    module.slider = lambda label, **kwargs: call_counts["slider"].append(label) or kwargs["value"]
    module.number_input = lambda label, **kwargs: call_counts["number_input"].append(label) or kwargs["value"]
    module.checkbox = lambda label, **kwargs: kwargs.get("value", False)
    module.text_input = lambda label, value="", **kwargs: value
    module.text_area = lambda label, **kwargs: "manual follow-up"
    module.file_uploader = lambda *args, **kwargs: None
    module.tabs = lambda vals: call_counts["tabs"].extend(vals) or [Ctx() for _ in vals]
    module.columns = lambda n: [Ctx() for _ in range(n)]
    module.expander = lambda *args, **kwargs: Ctx()
    module.selectbox = lambda label, options, **kwargs: list(options)[0]
    module.multiselect = lambda label, options, default=None, **kwargs: default

    def click(label, **kwargs):
        if label == "Review and explain this case" and review_button:
            call_counts["review"] += 1
            return True
        return False

    module.button = click
    return module, call_counts


def run_page(monkeypatch, fake, page):
    """Run a page with the Streamlit stub; re-import govlens.ui so it binds to the stub."""
    import govlens
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    monkeypatch.setattr(govlens.config, "get_api_key", lambda *a, **k: "")
    monkeypatch.delitem(sys.modules, "govlens.ui", raising=False)
    monkeypatch.delattr(govlens, "ui", raising=False)
    runpy.run_path(str(page), run_name="__main__")


def test_main_page_has_one_tab_per_check_and_reviews_cases(monkeypatch):
    fake, counts = fake_streamlit()
    run_page(monkeypatch, fake, APP_DIR / "views" / "review.py")
    assert counts["tabs"] == [
        "G2B: Spend across the 6-month reset", "G2C: Same cost centre and category", "Reason & justification",
    ]
    assert counts["review"] == 2  # one review button per rule tab
    for rule in ("G2B", "G2C"):
        review = fake.session_state[f"review-{rule}"]
        assert review["case_id"].startswith("GL-")
        assert "transaction IDs" in review["narrative"]
        assert {h.passage.doc for h in review["hits"]} == {"GG", "DG", "RS"}


def test_sidebar_has_no_fictitious_data_or_officer_cap_setting(monkeypatch):
    fake, counts = fake_streamlit(review_button=False)
    run_page(monkeypatch, fake, APP_DIR / "views" / "review.py")
    assert counts["radio"] == ["Masked QB sample (built-in)", "Upload QB CSV exports"]
    assert not any("cap" in label.lower() for label in counts["number_input"])
    assert any("cost-centre" in label for label in counts["number_input"])
    assert len(counts["slider"]) == 2


def test_reason_tab_shows_rule_flag_and_ai_tier_side_by_side(monkeypatch):
    fake, counts = fake_streamlit(review_button=False)
    run_page(monkeypatch, fake, APP_DIR / "views" / "review.py")
    tables = [d for d in counts["dataframes"] if hasattr(d, "columns") and {"Rule_Flag", "AI_Tier"} <= set(d.columns)]
    assert tables, "reason & justification table not rendered"
    table = tables[0]
    assert "Vague reason" in set(table["Rule_Flag"])
    assert set(table["AI_Tier"]) <= {"High", "Medium", "Uncertain", "Low", "Not screened", "Out of scope (#welfare)"}


APP_DIR = Path(__file__).parents[1]


def test_login_gate_blocks_pages_until_signed_in(monkeypatch):
    fake, _ = fake_streamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    with pytest.raises(SystemExit):
        runpy.run_path(str(APP_DIR / "app.py"), run_name="__main__")
    assert fake.navigation_state["pages"] is None and not fake.navigation_state["ran"]


def test_signed_in_user_gets_three_pages(monkeypatch):
    fake, _ = fake_streamlit()
    fake.session_state["authenticated"] = True
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    runpy.run_path(str(APP_DIR / "app.py"), run_name="__main__")
    pages = fake.navigation_state["pages"]
    assert [p.path for p in pages] == ["views/review.py", "views/about.py", "views/methodology.py"]
    assert [p.kwargs["title"] for p in pages] == ["Governance review", "About Us", "Methodology"]
    assert all((APP_DIR / p.path).exists() for p in pages)
    assert fake.navigation_state["ran"]


def test_password_check_uses_salted_hash(monkeypatch):
    salt = "00" * 16
    monkeypatch.setattr(govlens.auth, "PASSWORD_SALT", salt)
    monkeypatch.setattr(govlens.auth, "PASSWORD_HASH", govlens.auth.hash_password("test-password", salt))
    user = govlens.auth.USERNAME
    assert govlens.auth.verify(user, "test-password")
    assert govlens.auth.verify(f" {user.upper()} ", "test-password")
    assert not govlens.auth.verify(user, "wrong")
    assert not govlens.auth.verify("someone", "test-password")
    assert "test-password" not in (APP_DIR / "govlens" / "auth.py").read_text()


def test_credential_script_rewrites_username_and_password(tmp_path):
    sys.path.insert(0, str(APP_DIR / "scripts"))
    import importlib
    script = importlib.import_module("make_password_hash")
    auth_copy = tmp_path / "auth.py"
    original = (APP_DIR / "govlens" / "auth.py").read_text(encoding="utf-8")
    auth_copy.write_text(original, encoding="utf-8")
    script.update_auth_file(auth_copy, "  New.Admin ", "a-long-test-password")
    namespace = {}
    exec(auth_copy.read_text(encoding="utf-8"), namespace)
    assert namespace["USERNAME"] == "new.admin"
    assert namespace["verify"]("new.admin", "a-long-test-password")
    assert not namespace["verify"](govlens.auth.USERNAME, "a-long-test-password")
    assert "a-long-test-password" not in auth_copy.read_text(encoding="utf-8")
    for bad_user, bad_password in [("ab", "a-long-test-password"), ("ok-user", "short")]:
        before = auth_copy.read_text(encoding="utf-8")
        with pytest.raises(ValueError):
            script.update_auth_file(auth_copy, bad_user, bad_password)
        assert auth_copy.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("page", ["about.py", "methodology.py"])
def test_documentation_pages_render(monkeypatch, page):
    fake, _ = fake_streamlit()
    run_page(monkeypatch, fake, APP_DIR / "views" / page)


def test_main_page_shows_required_disclaimer():
    from govlens.ui_text import DISCLAIMER
    required = [
        "This web application is a prototype developed for educational purposes only.",
        "should not be relied upon for making any decisions, especially those related to financial, legal, or healthcare matters.",
        "the LLM may generate inaccurate or incorrect information. You assume full responsibility for how you use any generated output.",
        "Always consult with qualified professionals for accurate and personalised advice.",
    ]
    assert all(r in DISCLAIMER for r in required)
    assert "DISCLAIMER" in (APP_DIR / "views" / "review.py").read_text()


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz not installed")
@pytest.mark.parametrize("name", list(FLOWCHARTS))
def test_flowcharts_are_valid_dot(name):
    result = subprocess.run(["dot", "-Tsvg"], input=FLOWCHARTS[name], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_ai_explanation_requires_citation_from_retrieved_text(monkeypatch):
    cases, orders, detail, _ = analyse(*create_demo())
    case = cases[cases.Rule_ID.eq("G2B")].iloc[0]
    passages = [h.passage for h in retrieve(build_retriever(api_key=""), case)]
    source_id = passages[0].citation
    calls = []
    fake_module = ModuleType("openai")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = self

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text=f"Reference note [{source_id}]. QB purchase [QB:INV001].")

    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    text = openai_explanation(case, orders, detail, passages, api_key="TEST_FAKE_KEY")
    assert f"[{source_id}]" in text
    assert calls[0]["store"] is False
    assert calls[0]["model"] == "gpt-4o-mini"
    assert "retrieved_reference_passages" in calls[0]["input"]

    class InvalidFakeOpenAI(FakeOpenAI):
        def create(self, **kwargs):
            return SimpleNamespace(output_text="Unsupported source [GG-NOT-A-PASSAGE]")

    fake_module.OpenAI = InvalidFakeOpenAI
    with pytest.raises(ValueError, match="verifiable"):
        openai_explanation(case, orders, detail, passages, api_key="TEST_FAKE_KEY")


def test_justification_call_uses_strict_json_schema(monkeypatch):
    payload = {"cart_id": "C1", "items": [{"item_ref": "I1"}]}
    calls = []
    fake_module = ModuleType("openai")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = self

        def create(self, **kwargs):
            calls.append(kwargs)
            out = {"cart_id": "C1", "assessment": "ok", "assessment_summary": "ok",
                   "items": [{"item_ref": "I1", "core_function": "snack", "base_risk_level": "Low", "rationale": "fits"}]}
            return SimpleNamespace(output_text=json.dumps(out))

    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    out = js.call_openai(payload, "TEST_FAKE_KEY", "gpt-4o-mini")
    assert out["items"][0]["base_risk_level"] == "Low"
    fmt = calls[0]["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True
    assert calls[0]["store"] is False and calls[0]["temperature"] == 0


def test_api_key_lookup_order(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nexport OPENAI_API_KEY="from-dotenv"\n')
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert govlens.config.get_api_key(dotenv=env) == "from-dotenv"
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    assert govlens.config.get_api_key(dotenv=env) == "from-env"
    monkeypatch.delenv("OPENAI_API_KEY")
    assert govlens.config.get_api_key(lambda n: "from-secrets", dotenv=tmp_path / "none") == "from-secrets"
