#!/usr/bin/env python3
"""One-off migration: normalize self-referencing rows (child_domain == parent_domain) in
known-parent-child.csv into proper 'no parent found' records instead of self-parent 'Yes' rows.

Usage:
    python3 fix_self_parent_rows.py
"""
import csv
import os

from lib import no_parent_evidence

DB_FIELDS = [
    "child_name", "child_domain", "parent_name", "parent_domain",
    "verified", "evidence", "verification_method", "date_added",
]


def main():
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "known-parent-child.csv")
    with open(db_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fixed = 0
    for row in rows:
        if row["child_domain"] and row["child_domain"] == row["parent_domain"]:
            row["evidence"] = no_parent_evidence(row["child_name"], row["evidence"])
            row["parent_name"] = ""
            row["parent_domain"] = ""
            row["verified"] = "No"
            fixed += 1

    with open(db_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DB_FIELDS)
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["child_domain"]):
            w.writerow(r)

    print(f"Normalized {fixed} self-referencing rows to 'no parent found' out of {len(rows)} total")


if __name__ == "__main__":
    main()
