#!/usr/bin/env python3
"""Rebuild data/known-parent-child.csv from a Parent/Child export, keeping only confirmed relationships.

Usage:
    python3 build_known_db.py "../../Parent Child/Parent Child - Merged.csv"
"""
import argparse
import csv
import os

from lib import normalize_domain

OUT_FIELDS = [
    "child_name", "child_domain", "parent_name", "parent_domain",
    "verified", "evidence", "verification_method", "date_added",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source_csv")
    ap.add_argument(
        "-o", "--out",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "known-parent-child.csv"),
    )
    args = ap.parse_args()

    seen = {}
    with open(args.source_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("Parent Ownership Verified", "").strip().lower() != "yes":
                continue
            child_domain = normalize_domain(row.get("Child Company Domain Name", ""))
            parent_domain = normalize_domain(row.get("Parent Company Domain", ""))
            if not child_domain or not parent_domain:
                continue
            seen[child_domain] = {
                "child_name": row.get("Child Company Name", "").strip(),
                "child_domain": child_domain,
                "parent_name": (row.get("Parent Company Name") or row.get("Parent Company Name (2)") or "").strip(),
                "parent_domain": parent_domain,
                "verified": "Yes",
                "evidence": row.get("Verification Evidence", "").strip(),
                "verification_method": row.get("Verification Method", "").strip(),
                "date_added": row.get("Create Date", "").strip(),
            }

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        for rec in sorted(seen.values(), key=lambda r: r["child_domain"]):
            w.writerow(rec)

    print(f"Wrote {len(seen)} confirmed parent-child relationships to {args.out}")


if __name__ == "__main__":
    main()
