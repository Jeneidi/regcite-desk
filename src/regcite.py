"""Core retrieval, validation, and evaluation helpers for RegCite Desk."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rank_bm25 import BM25Okapi


SECTION_NONE = "none"
SECTION_LABELS = ("1005.11", "1026.13", SECTION_NONE)
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?")


class AgentAnswer(BaseModel):
    """Closed output schema used by the CLI adapter and browser demo."""

    model_config = ConfigDict(extra="forbid")

    section: Literal["1005.11", "1026.13", "none"]
    quote: str = Field(max_length=700)
    reason: str = Field(max_length=500)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def section_text(section: dict) -> str:
    return " ".join(section["paragraphs"])


class RegulationIndex:
    """Tiny BM25 index over the live eCFR paragraphs shipped with the demo."""

    def __init__(self, regulations: list[dict]):
        self.regulations = regulations
        self.paragraphs = [
            {"section": regulation["section"], "text": paragraph}
            for regulation in regulations
            for paragraph in regulation["paragraphs"]
        ]
        self.bm25 = BM25Okapi([tokenize(item["text"]) for item in self.paragraphs])

    def retrieve(self, complaint: str, top_k: int = 3) -> list[dict]:
        scores = self.bm25.get_scores(tokenize(complaint))
        ranked = sorted(
            zip(scores, self.paragraphs), key=lambda pair: pair[0], reverse=True
        )
        by_section: dict[str, dict] = {}
        for score, paragraph in ranked:
            current = by_section.get(paragraph["section"])
            if current is None:
                by_section[paragraph["section"]] = {
                    "section": paragraph["section"],
                    "score": float(score),
                    "paragraph": paragraph["text"],
                }
        return list(by_section.values())[:top_k]

    def top_section(self, complaint: str, threshold: float = 0.0) -> str:
        results = self.retrieve(complaint, top_k=1)
        if not results or results[0]["score"] <= threshold:
            return SECTION_NONE
        return results[0]["section"]


def validate_answer(answer: AgentAnswer, regulations: list[dict]) -> tuple[bool, str]:
    """Reject non-verbatim quotes and quotes from the wrong section."""

    if answer.section == SECTION_NONE:
        return (answer.quote == "", "refusal has no quote")
    if not answer.quote:
        return False, "a cited section needs a quote"
    regulation = next(
        (item for item in regulations if item["section"] == answer.section), None
    )
    if regulation is None:
        return False, "unknown section"
    if answer.quote not in section_text(regulation):
        return False, "quote is not an exact substring of the fetched eCFR section"
    return True, "verbatim quote matched fetched eCFR text"


def parse_answer(raw: str) -> AgentAnswer:
    """Parse the CLI result without accepting markdown or extra keys."""

    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValidationError.from_exception_data(
            "AgentAnswer", [{"type": "model_type", "loc": (), "input": value}]
        )
    return AgentAnswer.model_validate(value)


def load_json(path: str | Path):
    return json.loads(Path(path).read_text())


def evaluate(gold_cases: list[dict], predicted: list[dict], index: RegulationIndex) -> dict:
    """Compute the brief's headline and supporting metrics from recorded runs."""

    gold_by_id = {case["id"]: case for case in gold_cases}
    correct = 0
    baseline_correct = 0
    positive_total = 0
    recall_at_3 = 0
    verbatim_total = 0
    verbatim_ok = 0
    latencies = []
    rows = []
    for item in predicted:
        case = gold_by_id[item["id"]]
        gold = case["gold_section"]
        answer = AgentAnswer.model_validate(item["answer"])
        retrieved = item["retrieved"]
        predicted_section = answer.section if item["valid"] else SECTION_NONE
        baseline_section = index.top_section(case["narrative"])
        correct += predicted_section == gold
        baseline_correct += baseline_section == gold
        if gold != SECTION_NONE:
            positive_total += 1
            recall_at_3 += gold in {row["section"] for row in retrieved}
        if answer.section != SECTION_NONE:
            verbatim_total += 1
            verbatim_ok += item["valid"]
        latencies.append(float(item["latency_ms"]))
        rows.append(
            {
                "id": case["id"],
                "gold": gold,
                "predicted": predicted_section,
                "baseline": baseline_section,
                "valid_quote": item["valid"],
            }
        )
    latencies.sort()
    median_latency = latencies[len(latencies) // 2] if latencies else 0.0
    total = len(gold_cases)
    return {
        "total": total,
        "agent_accuracy": correct / total if total else 0.0,
        "baseline_accuracy": baseline_correct / total if total else 0.0,
        "retrieval_recall_at_3": recall_at_3 / positive_total if positive_total else 0.0,
        "verbatim_quote_rate": verbatim_ok / verbatim_total if verbatim_total else 1.0,
        "verbatim_quote_count": verbatim_ok,
        "verbatim_quote_total": verbatim_total,
        "median_latency_ms": median_latency,
        "cash_cost_usd": 0.0,
        "rows": rows,
    }
