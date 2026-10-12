"""Run the cached Claude agent over the 60 category-labeled CFPB cases."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.regcite import AgentAnswer, RegulationIndex, evaluate, load_json, validate_answer


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
CACHE = DATA / "llm_cache"
MODEL_LABEL = "Claude Haiku 5.5 via Claude Code"


def cache_key(case: dict, retrieved: list[dict]) -> str:
    payload = json.dumps({"prompt_version": "full-section-v2", "narrative": case["narrative"], "retrieved": retrieved}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def prompt_for(case: dict, retrieved: list[dict], regulations: list[dict]) -> str:
    candidates = "\n\n".join(
        f"SECTION {regulation['section']}\n{chr(10).join(regulation['paragraphs'])}" for regulation in regulations
    )
    return f"""You are a compliance triage assistant. You are not a lawyer and must not invent a rule.
Return only one JSON object with exactly these keys: section, quote, reason.
section must be exactly 1005.11, 1026.13, or none.
Use only the candidate eCFR paragraphs below. Choose 1005.11 only when the complaint clearly describes an electronic fund transfer or account error. Choose 1026.13 only when it clearly describes a credit card billing error. Otherwise choose none.
When citing a section, copy one complete sentence or paragraph exactly from that candidate text, including punctuation. When refusing, quote must be the empty string.
Complaint product: {case['product']}
Complaint issue: {case['issue']}
Complaint narrative: {case['narrative']}

Candidate eCFR text:
{candidates}
"""


def run_claude(prompt: str) -> tuple[dict, float, str]:
    started = time.perf_counter()
    result = subprocess.run(
        ["claude", "-p", "--model", "claude-haiku-5-5", "--output-format", "json", prompt],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    envelope = json.loads(result.stdout)
    raw_answer = envelope.get("result", "")
    try:
        return json.loads(raw_answer), latency_ms, result.stderr.strip()
    except json.JSONDecodeError:
        start = raw_answer.find("{")
        end = raw_answer.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw_answer[start : end + 1]), latency_ms, result.stderr.strip()
            except json.JSONDecodeError:
                pass
        return {"section": "none", "quote": "", "reason": "model response was not valid JSON"}, latency_ms, result.stderr.strip()


def main() -> None:
    cases = load_json(DATA / "eval_cases.json")
    regulations = load_json(DATA / "regulations.json")
    index = RegulationIndex(regulations)
    CACHE.mkdir(parents=True, exist_ok=True)
    runs = []
    llm_calls = 0
    for count, case in enumerate(cases, start=1):
        retrieved = index.retrieve(case["narrative"], top_k=3)
        key = cache_key(case, retrieved)
        cache_file = CACHE / f"{key}.json"
        if cache_file.exists():
            cached = json.loads(cache_file.read_text())
            answer_data = cached["answer"]
            latency_ms = cached["latency_ms"]
            stderr = cached.get("stderr", "")
        else:
            answer_data, latency_ms, stderr = run_claude(prompt_for(case, retrieved, regulations))
            cache_file.write_text(json.dumps({"answer": answer_data, "latency_ms": latency_ms, "stderr": stderr}, indent=2) + "\n")
            llm_calls += 1
        try:
            answer = AgentAnswer.model_validate(answer_data)
            valid, validation = validate_answer(answer, regulations)
        except Exception as error:
            answer = AgentAnswer(section="none", quote="", reason=f"schema failure: {error}")
            valid, validation = False, "schema failure"
        runs.append(
            {
                "id": case["id"],
                "answer": answer.model_dump(),
                "retrieved": retrieved,
                "valid": valid,
                "validation": validation,
                "latency_ms": latency_ms,
                "model": MODEL_LABEL,
                "recorded_date": str(date.today()),
            }
        )
        print(f"{count:02d}/60 {case['id']} {answer.section} valid={valid} {latency_ms:.0f}ms")
    metrics = evaluate(cases, runs, index)
    metrics["model"] = MODEL_LABEL
    metrics["recorded_date"] = str(date.today())
    metrics["llm_calls_used"] = llm_calls
    metrics["llm_calls_total"] = len(cases)
    metrics["llm_calls_cached"] = len(cases) - llm_calls
    (DATA / "agent_runs.json").write_text(json.dumps(runs, indent=2, ensure_ascii=False) + "\n")
    recorded_ids = {case["id"] for case in load_json(DATA / "recorded_cases.json")}
    (DATA / "recorded_runs.json").write_text(json.dumps([run for run in runs if run["id"] in recorded_ids], indent=2, ensure_ascii=False) + "\n")
    (DATA / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({key: metrics[key] for key in metrics if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
