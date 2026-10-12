"""Build a small, reproducible CFPB and eCFR fixture from the official sources."""

from __future__ import annotations

import csv
import gzip
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
OUT = ROOT / "site" / "data"

# Fixed mapping from the consumer-selected CFPB category to the evaluation label.
# Empty issue and sub_issue values mean every complaint under that product.
LABEL_TABLE = (
    {"label": "1026.13", "product": "Credit card or prepaid card", "issue": "Problem with a purchase shown on your statement", "sub_issue": "", "none_kind": ""},
    {"label": "1005.11", "product": "Checking or savings account", "issue": "Problem with a lender or other company charging your account", "sub_issue": "", "none_kind": ""},
    {"label": "1005.11", "product": "Checking or savings account", "issue": "", "sub_issue": "Banking errors", "none_kind": ""},
    {"label": "1005.11", "product": "Checking or savings account", "issue": "", "sub_issue": "Problem using a debit or ATM card", "none_kind": ""},
    {"label": "1005.11", "product": "Money transfer, virtual currency, or money service", "issue": "Unauthorized transactions or other transaction problem", "sub_issue": "", "none_kind": ""},
    {"label": "none", "product": "Credit card or prepaid card", "issue": "Advertising and marketing, including promotional offers", "sub_issue": "", "none_kind": "near_miss"},
    {"label": "none", "product": "Credit card or prepaid card", "issue": "Getting a credit card", "sub_issue": "", "none_kind": "near_miss"},
    {"label": "none", "product": "Credit card or prepaid card", "issue": "Closing your account", "sub_issue": "", "none_kind": "near_miss"},
    {"label": "none", "product": "Checking or savings account", "issue": "Opening an account", "sub_issue": "", "none_kind": "near_miss"},
    {"label": "none", "product": "Checking or savings account", "issue": "Closing an account", "sub_issue": "", "none_kind": "near_miss"},
    {"label": "none", "product": "Mortgage", "issue": "", "sub_issue": "", "none_kind": "other_product"},
    {"label": "none", "product": "Debt collection", "issue": "", "sub_issue": "", "none_kind": "other_product"},
)


def label_for(row: dict) -> tuple[str, str]:
    for rule in LABEL_TABLE:
        if row.get("Product", "") != rule["product"]:
            continue
        if rule["issue"] and row.get("Issue", "") != rule["issue"]:
            continue
        if rule["sub_issue"] and row.get("Sub-issue", "") != rule["sub_issue"]:
            continue
        return rule["label"], rule["none_kind"]
    return "", ""


def clean_text(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def choose_cases() -> list[dict]:
    source = RAW / "CCDB_Export_2_May_2018_through_April_2021.zip"
    limits = {"1005.11": 20, "1026.13": 20, "none": 20}
    none_limits = {"near_miss": 10, "other_product": 10}
    picked: dict[str, list[dict]] = {label: [] for label in limits}
    none_counts = {kind: 0 for kind in none_limits}
    seen: set[str] = set()
    with zipfile.ZipFile(source) as archive, archive.open(archive.namelist()[0]) as handle:
        rows = csv.DictReader((line.decode("utf-8-sig") for line in handle))
        for row in rows:
            narrative = clean_text(row.get("Consumer complaint narrative", ""))
            if len(narrative) < 80:
                continue
            complaint_id = row["Complaint ID"]
            if complaint_id in seen:
                continue
            label, none_kind = label_for(row)
            if not label or len(picked[label]) >= limits[label]:
                continue
            if label == "none" and none_counts[none_kind] >= none_limits[none_kind]:
                continue
            seen.add(complaint_id)
            picked[label].append(
                {
                    "id": complaint_id,
                    "gold_section": label,
                    "none_kind": none_kind,
                    "product": row.get("Product", ""),
                    "sub_product": row.get("Sub-product", ""),
                    "issue": row.get("Issue", ""),
                    "company": row.get("Company", ""),
                    "date_received": row.get("Date received", ""),
                    "narrative": narrative,
                    "source_url": "https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/",
                    "label_basis": "consumer-selected CFPB issue category mapped by the table in the README",
                }
            )
            if label == "none":
                none_counts[none_kind] += 1
            if all(len(picked[key]) == limit for key, limit in limits.items()):
                break
    if any(len(picked[key]) != limit for key, limit in limits.items()):
        raise RuntimeError({key: len(value) for key, value in picked.items()})
    cases = picked["1005.11"] + picked["1026.13"] + picked["none"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eval_cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    none_demo = [next(case for case in picked["none"] if case["none_kind"] == kind) for kind in ("near_miss", "other_product")]
    recorded_source = picked["1005.11"][:3] + picked["1026.13"][:3] + none_demo
    recorded = [{key: value for key, value in case.items() if key not in {"gold_section", "label_basis", "none_kind"}} for case in recorded_source]
    (OUT / "recorded_cases.json").write_text(json.dumps(recorded, indent=2) + "\n")
    return cases


def xml_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")


def build_regulations() -> list[dict]:
    rows = []
    for section, title, filename, url in [
        (
            "1005.11",
            "Procedures for resolving errors",
            "ecfr_1005_11.xml",
            "https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-12.xml?part=1005&section=1005.11",
        ),
        (
            "1026.13",
            "Billing error resolution",
            "ecfr_1026_13.xml",
            "https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-12.xml?part=1026&section=1026.13",
        ),
    ]:
        root = ElementTree.fromstring(xml_text(RAW / filename))
        paragraphs = [clean_text("".join(element.itertext())) for element in root.findall(".//P")]
        rows.append({"section": section, "title": title, "url": url, "paragraphs": paragraphs})
    (OUT / "regulations.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    return rows


if __name__ == "__main__":
    cases = choose_cases()
    regulations = build_regulations()
    print(json.dumps({"cases": len(cases), "by_section": {label: sum(c["gold_section"] == label for c in cases) for label in ["1005.11", "1026.13", "none"]}, "none_kinds": {kind: sum(c["none_kind"] == kind for c in cases) for kind in ["near_miss", "other_product"]}, "regulations": [r["section"] for r in regulations]}, indent=2))
