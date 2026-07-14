---
name: parent-child
description: "Given a CSV of companies, find each one's parent/owning company. Checks a known-relationships database first, then resolves anything unknown via web search + LLM reasoning, and grows the database with what it finds. Use when someone uploads a company list and asks for parent companies, ownership mapping, or account consolidation."
---

# Parent Company Finder

Takes a CSV of companies (e.g. a CRM export) and returns the same list with each
company's parent/owning company filled in. Reuses everything already confirmed
in `data/known-parent-child.csv`, and only spends web-search/LLM effort on
companies that haven't been resolved before — then saves those new findings so
the next run needs less lookup work.

## Input

A CSV with at least one column containing a company domain (header must contain
the word "domain", e.g. `Company Domain Name`, `Child Company Domain Name`). A
company name column is used for readability but isn't required for matching —
matching is always by domain.

## Workflow

### Step 1 — Match against the known database

```
python3 scripts/match_known.py <input.csv> --matched-out matched.csv --unmatched-out unmatched.csv
```

This normalizes each input domain (strips scheme/`www.`/path) and looks it up
in `data/known-parent-child.csv`. Anything found is written to `matched.csv`
with `Parent Company Name`, `Parent Company Domain`, `Verified`, `Evidence`
columns already filled in — no LLM/search cost for these.

Everything else lands in `unmatched.csv` for step 2.

### Step 2 — Resolve the unmatched companies (agent-driven, not scripted)

For each row in `unmatched.csv`, use WebSearch + reasoning to identify the
parent/owning company. This step is intentionally not a script — it needs
judgment. For each company:

1. Search for evidence of acquisition, ownership, or subsidiary status
   (e.g. `"<company>" acquired by`, `"<company>" parent company`, `"<company>"
   subsidiary of`).
2. Decide `Verified`:
   - **Yes** — found a specific, citable acquisition/ownership fact (who
     bought it, when, or an explicit "X is a subsidiary of Y" statement).
   - **Maybe** — plausible connection but no solid citation (e.g. similar
     branding, ambiguous search results).
   - **No** — no evidence of any parent; the company appears independent, or
     the search only surfaced unrelated/coincidental name matches.
3. Write one line of `Evidence` explaining the verdict (this is what gets
   stored in the database for future audits — see the existing
   `data/known-parent-child.csv` for the tone/format to match).
4. A company can be its own parent when it has no separate owner — in that
   case set `Parent Company Name`/`Parent Company Domain` to the company's own
   name/domain and note it in `Evidence` (this mirrors the "heuristic" rows
   already in the database).

Batch companies sensibly (a handful of searches at a time) rather than doing
exhaustive research on every row — match the depth of the original manual
passes (see `verification_method` values like `LLM+web search` in the
database).

Build `findings.csv`: same columns as `unmatched.csv`, plus `Parent Company
Name`, `Parent Company Domain`, `Verified`, `Evidence`.

### Step 3 — Merge results and grow the database

```
python3 scripts/apply_findings.py matched.csv findings.csv --final-out final-output.csv
```

This:
- Concatenates `matched.csv` + `findings.csv` into `final-output.csv` — the
  deliverable, with every input row now carrying a parent company (or a
  `Verified: No`/`Maybe` note if none was found).
- Appends only the **Verified: Yes** rows from `findings.csv` into
  `data/known-parent-child.csv` (deduped by child domain), so the next CSV run
  through this skill has fewer unmatched companies.

## Database schema (`data/known-parent-child.csv`)

| Column | Meaning |
|---|---|
| `child_name` | Company name |
| `child_domain` | Normalized company domain (matching key) |
| `parent_name` | Parent/owning company name |
| `parent_domain` | Parent/owning company domain |
| `verified` | Always `Yes` in this file — only confirmed relationships are stored |
| `evidence` | One-line justification |
| `verification_method` | How it was confirmed (e.g. `LLM+web search`, `Heuristic`) |
| `date_added` | When the relationship was confirmed |

Only confirmed (`Yes`) relationships live here on purpose — `Maybe`/`No`
verdicts stay in that run's `final-output.csv` but are never persisted, so the
database doesn't accumulate unreliable data.

## Rebuilding the database from a fresh export

If a newer manually-verified export replaces the one this was seeded from:

```
python3 scripts/build_known_db.py "<path to export CSV>"
```

This was originally seeded from `../Parent Child/Parent Child - Merged.csv`
(3,560 confirmed relationships as of 2026-07-14), filtering to rows where
`Parent Ownership Verified == Yes` and dropping all HubSpot-specific fields.

## Files

```
parent-child-skill/
  SKILL.md
  data/
    known-parent-child.csv     # the growing database of confirmed relationships
  scripts/
    lib.py                     # domain normalization + column-detection helpers
    build_known_db.py          # (re)build the database from a verified export
    match_known.py             # step 1: split input into matched / unmatched
    apply_findings.py          # step 3: merge results + grow the database
```
