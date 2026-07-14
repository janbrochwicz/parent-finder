#!/usr/bin/env python3
"""Check an input company list against the known parent-child database.

Splits the input into:
  - matched.csv    rows where the domain was already in the known DB (parent columns filled in)
  - unmatched.csv  rows with no known parent yet (need a WebSearch/LLM lookup)

Usage:
    python3 match_known.py path/to/input.csv --matched-out matched.csv --unmatched-out unmatched.csv
"""
import argparse
import csv
import os

from lib import normalize_domain, find_column

DOMAIN_KEYWORDS = ["domain"]
NAME_KEYWORDS = ["company name", "name"]


def load_known(db_path):
    known = {}
    with open(db_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            known[row["child_domain"]] = row
    return known


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv")
    ap.add_argument(
        "-d", "--db",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "known-parent-child.csv"),
    )
    ap.add_argument("--matched-out", default="matched.csv")
    ap.add_argument("--unmatched-out", default="unmatched.csv")
    args = ap.parse_args()

    known = load_known(args.db)

    with open(args.input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    domain_col = find_column(fieldnames, DOMAIN_KEYWORDS)
    if not domain_col:
        raise SystemExit(f"Could not find a domain column in input headers: {fieldnames}")

    matched_fields = fieldnames + ["Parent Company Name", "Parent Company Domain", "Verified", "Evidence"]
    matched, unmatched = [], []

    for row in rows:
        domain = normalize_domain(row.get(domain_col, ""))
        hit = known.get(domain)
        if hit:
            out = dict(row)
            out["Parent Company Name"] = hit["parent_name"]
            out["Parent Company Domain"] = hit["parent_domain"]
            out["Verified"] = "Yes"
            out["Evidence"] = hit["evidence"]
            matched.append(out)
        else:
            unmatched.append(row)

    with open(args.matched_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=matched_fields)
        w.writeheader()
        w.writerows(matched)

    with open(args.unmatched_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(unmatched)

    print(f"{len(matched)} matched from known DB -> {args.matched_out}")
    print(f"{len(unmatched)} need a lookup -> {args.unmatched_out}")


if __name__ == "__main__":
    main()
