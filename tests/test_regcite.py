import json
import inspect
from pathlib import Path

import scripts.prepare_data as prepare_data
from src.regcite import AgentAnswer, RegulationIndex, evaluate, validate_answer


ROOT = Path(__file__).resolve().parents[1]
REGULATIONS = json.loads((ROOT / "site/data/regulations.json").read_text())


def test_exact_quote_gate_accepts_and_rejects():
    regulation = REGULATIONS[0]
    good = AgentAnswer(section="1005.11", quote=regulation["paragraphs"][0], reason="matched")
    bad = AgentAnswer(section="1005.11", quote="A paraphrase that is not in the law.", reason="matched")
    assert validate_answer(good, REGULATIONS)[0]
    assert not validate_answer(bad, REGULATIONS)[0]


def test_closed_schema_rejects_extra_keys():
    try:
        AgentAnswer.model_validate({"section": "none", "quote": "", "reason": "", "extra": 1})
    except Exception as error:
        assert "extra" in str(error)
    else:
        raise AssertionError("extra schema keys must be rejected")


def test_retrieval_returns_both_sections_for_distinct_terms():
    index = RegulationIndex(REGULATIONS)
    assert index.retrieve("unauthorized electronic transfer", top_k=3)[0]["section"] == "1005.11"
    assert index.retrieve("credit card billing error statement", top_k=3)[0]["section"] == "1026.13"


def test_metric_math_is_exact():
    cases = [
        {"id": "a", "gold_section": "1005.11", "narrative": "unauthorized electronic transfer"},
        {"id": "b", "gold_section": "none", "narrative": "credit card marketing message, not a billing dispute"},
    ]
    predicted = [
        {"id": "a", "answer": {"section": "1005.11", "quote": REGULATIONS[0]["paragraphs"][0], "reason": ""}, "retrieved": [{"section": "1005.11"}], "valid": True, "latency_ms": 10},
        {"id": "b", "answer": {"section": "none", "quote": "", "reason": ""}, "retrieved": [{"section": "1026.13"}], "valid": True, "latency_ms": 30},
    ]
    result = evaluate(cases, predicted, RegulationIndex(REGULATIONS))
    assert result["agent_accuracy"] == 1.0
    assert result["baseline_accuracy"] == 1.0
    assert result["baseline_threshold0_accuracy"] == 0.5
    assert result["median_latency_ms"] == 30


def test_recorded_demo_does_not_ship_eval_labels():
    recorded = json.loads((ROOT / "site/data/recorded_cases.json").read_text())
    assert len(recorded) == 8
    assert all("gold_section" not in case and "label_basis" not in case for case in recorded)


def test_cfpb_label_table_maps_categories_without_narrative_regex():
    examples = [
        {"Product": "Credit card or prepaid card", "Issue": "Problem with a purchase shown on your statement"},
        {"Product": "Checking or savings account", "Issue": "Managing an account", "Sub-issue": "Banking errors"},
        {"Product": "Money transfer, virtual currency, or money service", "Issue": "Unauthorized transactions or other transaction problem"},
        {"Product": "Credit card or prepaid card", "Issue": "Closing your account"},
        {"Product": "Mortgage", "Issue": "Trouble during payment process"},
    ]
    assert [prepare_data.label_for(row) for row in examples] == [
        ("1026.13", ""),
        ("1005.11", ""),
        ("1005.11", ""),
        ("none", "near_miss"),
        ("none", "other_product"),
    ]
    source = inspect.getsource(prepare_data.choose_cases)
    assert "REG_E_WORDS" not in source
    assert "REG_Z_WORDS" not in source
    assert "search(" not in source
    assert "findall(" not in source
