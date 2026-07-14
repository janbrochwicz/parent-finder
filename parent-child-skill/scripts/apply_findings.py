#!/usr/bin/env python3
"""Merge WebSearch/LLM findings with the known-DB matches into one final output,
and grow the known database with any newly confirmed relationships.

`findings_csv` must have the same columns as unmatched.csv (from match_known.py)
plus: Parent Company Name, Parent Company Domain, Verified (Yes/No/Maybe), Evidence.

Usage:
    python3 apply_findings.py matched.csv findings.csv --final-out final-output.csv
"""
import argparse
import csv
import datetime
import os

from lib import normalize_domain, find_column

DB_FIELDS = [
    "child_name", "child_domain", "parent_name", "parent_domain",
    "verified", "evidence", "verification_method", "date_added",
]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r), r.fieldnames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("matched_csv")
    ap.add_argument("findings_csv")
    ap.add_argument(
        "-d", "--db",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "known-parent-child.csv"),
    )
    ap.add_argument("-o", "--final-out", default="final-output.csv")
    args = ap.parse_args()

    matched, matched_fields = read_csv(args.matched_csv)
    findings, findings_fields = read_csv(args.findings_csv)
    fieldnames = matched_fields or findings_fields

    with open(args.final_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(matched)
        w.writerows(findings)

    name_col = find_column(findings_fields, ["company name", "name"])
    domain_col = find_column(findings_fields, ["domain"])

    existing = {}
    if os.path.exists(args.db):
        db_rows, _ = read_csv(args.db)
        existing = {r["child_domain"]: r for r in db_rows}

    today = datetime.date.today().isoformat()
    added = 0
    for row in findings:
        if row.get("Verified", "").strip().lower() != "yes":
            continue
        child_domain = normalize_domain(row.get(domain_col, ""))
        parent_domain = normalize_domain(row.get("Parent Company Domain", ""))
        if not child_domain or not parent_domain or child_domain in existing:
            continue
        existing[child_domain] = {
            "child_name": row.get(name_col, "").strip(),
            "child_domain": child_domain,
            "parent_name": row.get("Parent Company Name", "").strip(),
            "parent_domain": parent_domain,
            "verified": "Yes",
            "evidence": row.get("Evidence", "").strip(),
            "verification_method": "LLM+web search",
            "date_added": today,
        }
        added += 1

    with open(args.db, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DB_FIELDS)
        w.writeheader()
        for rec in sorted(existing.values(), key=lambda r: r["child_domain"]):
            w.writerow(rec)

    print(f"Final output: {len(matched) + len(findings)} rows -> {args.final_out}")
    print(f"Known DB grown by {added} newly confirmed relationships -> {args.db}")


if __name__ == "__main__":
    main()
