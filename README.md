# RegCite Desk

An AI agent that retrieves the federal rule for a CFPB complaint, quotes fetched eCFR text verbatim, or refuses to cite when the evidence does not fit.

Live demo: https://regcite-desk.mjeneidi.com

## The problem

Banks route complaints and disputes under Regulation E and Regulation Z deadlines. An LLM that paraphrases a regulation incorrectly or invents a rule can turn a routing shortcut into a compliance incident.

## The result

On 60 CFPB narratives labeled from the consumer-selected Product, Issue, and Sub-issue fields, the recorded Claude agent reached 75% accuracy versus 35% for a BM25 baseline tuned on these same 60 cases. The threshold-0 BM25 reference reached 33.33333333333333%.

The agent recalled 65% of 1005.11 cases, 65% of 1026.13 cases, and 95% of none cases. It reached 100% accuracy on the 10 near-miss none cases, versus 10% for tuned BM25 and 0% for threshold-0 BM25. Retrieval recall at 3 was 100%, and all 29 cited outputs passed the exact substring check. Median model latency was 8801.04 ms and cash cost was $0.00.

## How it works

1. Read public CFPB complaint narratives and the consumer-selected category fields from the official archive.
2. Map fixed Product, Issue, and Sub-issue combinations to 1005.11, 1026.13, or none, then take the first 20 rows per class with 10 near misses and 10 other-product none cases.
3. Split two eCFR sections into paragraphs and rank them with BM25.
4. Ask Claude Haiku 5.5 for closed JSON naming one section, one exact quote, and one reason.
5. Validate the schema and reject any quote that is not a literal substring of the fetched section before human review.

## Data and license

The complaint narratives and category fields come from the [CFPB Consumer Complaint Database Narratives Archive](https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/). CFPB documents Product, Issue, and Sub-issue as the consumer's selections in its [data-use documentation](https://www.consumerfinance.gov/complaint/data-use/). The archive is an official public record of narratives published after CFPB PII scrubbing.

The regulation text comes from the [eCFR versioner API for 12 CFR 1005.11](https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-12.xml?part=1005&section=1005.11) and the [eCFR versioner API for 12 CFR 1026.13](https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-12.xml?part=1026&section=1026.13). Both are public-domain U.S. government sources.

The fixed mapping table used by `scripts/prepare_data.py` is:

| Label | Product | Issue | Sub-issue | None kind |
|---|---|---|---|---|
| 1026.13 | Credit card or prepaid card | Problem with a purchase shown on your statement |  |  |
| 1005.11 | Checking or savings account | Problem with a lender or other company charging your account |  |  |
| 1005.11 | Checking or savings account |  | Banking errors |  |
| 1005.11 | Checking or savings account |  | Problem using a debit or ATM card |  |  |
| 1005.11 | Money transfer, virtual currency, or money service | Unauthorized transactions or other transaction problem |  |  |
| none | Credit card or prepaid card | Advertising and marketing, including promotional offers |  | near_miss |
| none | Credit card or prepaid card | Getting a credit card |  | near_miss |
| none | Credit card or prepaid card | Closing your account |  | near_miss |
| none | Checking or savings account | Opening an account |  | near_miss |
| none | Checking or savings account | Closing an account |  | near_miss |
| none | Mortgage |  |  | other_product |
| none | Debt collection |  |  | other_product |

Each case carries the label basis: `consumer-selected CFPB issue category mapped by the table in the README`.

## Evaluation method

The evaluation has 20 cases per class. The baseline ranks the two sections with BM25 and returns none when the top score is at or below a cutoff. The tuned cutoff is `17.42344988843139`, selected to maximize baseline accuracy on these same 60 cases. This test-set tuning flatters the baseline. The threshold-0 version is reported separately for reference.

| Metric | Agent | Tuned BM25 | Threshold-0 BM25 |
|---|---:|---:|---:|
| Overall accuracy | 75% | 35% | 33.33333333333333% |
| Recall, 1005.11 | 65% | 70% | 75% |
| Recall, 1026.13 | 65% | 25% | 25% |
| Recall, none | 95% | 10% | 0% |
| Near-miss none accuracy | 100% | 10% | 0% |

Supporting metrics: retrieval recall at 3 was 100%, verbatim quote rate was 100% (29/29 cited outputs), median latency was 8801.04 ms, and cash cost was $0.00. The prompt stayed at `full-section-v2`, and the final corrected run used 2 new Claude CLI calls with 58 cached responses. No prompt revision was needed.

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

The labels are consumer-selected CFPB categories, not a lawyer's judgment about whether a complaint describes a legal violation. CFPB complaint narratives are unverified allegations and represent one side of an issue. The corpus covers only 12 CFR 1005.11 and 12 CFR 1026.13, not every provision in Parts 1005 and 1026. Every result still needs human review.

The site default uses committed recorded JSON and needs no key. The live BYOK path stores a provider key only in sessionStorage and was browser-checked in its no-key state. The corrected run itself used no paid API and no `api.openai.com` call. Two overlapping discarded evaluation attempts were started before the none split was corrected, consuming 76 Claude CLI calls combined; the final corrected run added 2, for 78 CLI calls in this fix. No prompt revision was made.

## Credits

Built by Mohammad Jeneidi with Python, pydantic, rank_bm25, the CFPB public data archive, eCFR, and a plain HTML, CSS, and JavaScript site.
