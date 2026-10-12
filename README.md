# RegCite Desk

An AI agent that retrieves the federal rule for a CFPB complaint, quotes the fetched eCFR text verbatim, or refuses to cite when the evidence does not fit.

Live demo: https://regcite-desk.mjeneidi.com

## The problem

Banks route complaints and disputes under Regulation E and Regulation Z deadlines. An LLM that paraphrases a regulation incorrectly or invents a rule can turn a routing shortcut into a compliance incident.

## The result

On 60 hand-reviewed CFPB narratives, the recorded Claude agent agreed with the labels on 40% of cases versus 50% for the BM25 top-1 baseline. BM25 retrieval recall at 3 was 100%, every one of 18 cited recorded outputs passed the exact substring check, median model latency was 8,050.18 ms, and the cash cost was $0.00.

These labels measure agreement with a small portfolio evaluation, not legal correctness. The result is useful because it exposes the gap between retrieval and judgment instead of hiding it.

## How it works

1. Fetch public CFPB complaint narratives from the official archive and two current eCFR section endpoints.
2. Split the eCFR text into paragraphs and rank them with BM25.
3. Ask Claude Haiku 5.5 for closed JSON naming one section, one exact quote, and one reason.
4. Validate the schema and reject any quote that is not a literal substring of the fetched section.
5. Show the evidence and wait for a human reviewer.

## Data and license

The complaint narratives come from the [CFPB Consumer Complaint Database Narratives Archive](https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/). The archive is an official public-domain record of narratives previously published by CFPB after PII scrubbing. Current CFPB metadata remains available from the [bulk complaint download](https://files.consumerfinance.gov/ccdb/complaints.csv.zip).

The regulation text comes from the [eCFR versioner API](https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-12.xml?part=1005&section=1005.11) for 12 CFR 1005.11 and the [12 CFR 1026.13 endpoint](https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-12.xml?part=1026&section=1026.13). Both are public-domain U.S. government sources.

## Evaluation method

The evaluation has 30 Reg E cases, 20 Reg Z cases, and 10 refusal cases. The labels were manually reviewed for this project and were not used to tune the recorded run. The baseline is BM25 top-1 with a zero-score refusal. Supporting metrics are retrieval recall at 3, exact quote rate, median latency, and cash cost.

## How to run

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -r requirements.txt
./.venv/bin/python scripts/prepare_data.py
./.venv/bin/python scripts/run_eval.py
./.venv/bin/python -m pytest -q
python3 -m http.server 8000 --bind 127.0.0.1 --directory site
```

The raw archives are ignored by git. `scripts/prepare_data.py` rebuilds the small JSON fixtures after the source archives are downloaded into `raw/`. LLM responses are cached in `site/data/llm_cache/` so evaluation reruns do not spend another call.

## Limitations

CFPB stopped publishing new complaint narratives in August 2026, so this build uses the official FOIA archive of previously published narratives instead of the current metadata-only bulk export. The corpus is limited to 12 CFR 1005.11 and 12 CFR 1026.13, not every provision in Parts 1005 and 1026. Complaint labels are an agreement test, not legal advice or a verified finding about a company. The live BYOK path is a browser demo and every result still needs human review.

The final recorded evaluation used 60 Claude Haiku 5.5 calls through Claude Code, with no paid API and no API key read from the machine. The site default uses committed recorded JSON and needs no key.

## Credits

Built by Mohammad Jeneidi with Python, pydantic, rank_bm25, the CFPB public data archive, eCFR, and a plain HTML, CSS, and JavaScript site.
