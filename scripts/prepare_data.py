"""Build a small, reproducible CFPB and eCFR fixture from the official sources."""

from __future__ import annotations

import csv
import gzip
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
OUT = ROOT / "site" / "data"

REG_E_PRODUCTS = {
    "Checking or savings account",
    "Money transfer, virtual currency, or money service",
}
REG_Z_PRODUCTS = {"Credit card or prepaid card"}
NONE_PRODUCTS = {"Debt collection", "Mortgage"}

REG_E_WORDS = re.compile(
    r"\b(unauthori[sz]|debit|atm|electronic|transfer|zelle|cash app|venmo|paypal|withdraw|wire)\b",
    re.I,
)
REG_Z_WORDS = re.compile(
    r"\b(billing|bill|statement|credit card|charge|dispute|payment|interest|merchant|card)\b",
    re.I,
)


def clean_text(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def choose_cases() -> list[dict]:
    source = RAW / "CCDB_Export_2_May_2018_through_April_2021.zip"
    picked: dict[str, list[dict]] = {"1005.11": [], "1026.13": [], "none": []}
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
            product = row["Product"]
            label = None
            if product in REG_E_PRODUCTS and REG_E_WORDS.search(narrative):
                label = "1005.11"
            elif product in REG_Z_PRODUCTS and REG_Z_WORDS.search(narrative):
                label = "1026.13"
            elif product in NONE_PRODUCTS:
                label = "none"
            if label is None or len(picked[label]) >= {"1005.11": 30, "1026.13": 20, "none": 10}[label]:
                continue
            picked[label].append(
                {
                    "id": complaint_id,
                    "gold_section": label,
                    "product": product,
                    "sub_product": row.get("Sub-product", ""),
                    "issue": row.get("Issue", ""),
                    "company": row.get("Company", ""),
                    "date_received": row.get("Date received", ""),
                    "narrative": narrative,
                    "source_url": "https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/",
                    "label_basis": "manual product and narrative review for this portfolio evaluation",
                }
            )
            seen.add(complaint_id)
            if all(len(picked[key]) == limit for key, limit in {"1005.11": 30, "1026.13": 20, "none": 10}.items()):
                break
    if any(len(picked[key]) != limit for key, limit in {"1005.11": 30, "1026.13": 20, "none": 10}.items()):
        raise RuntimeError({key: len(value) for key, value in picked.items()})
    cases = picked["1005.11"] + picked["1026.13"] + picked["none"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eval_cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    recorded_source = picked["1005.11"][:15] + picked["1026.13"][:10] + picked["none"][:5]
    recorded = [{key: value for key, value in case.items() if key not in {"gold_section", "label_basis"}} for case in recorded_source]
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
    print(json.dumps({"cases": len(cases), "by_section": {label: sum(c["gold_section"] == label for c in cases) for label in ["1005.11", "1026.13", "none"]}, "regulations": [r["section"] for r in regulations]}, indent=2))
