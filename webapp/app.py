import csv
import datetime
import io
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from supabase import create_client

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = BASE_DIR / "parent-child-skill"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from lib import find_column, no_parent_evidence, normalize_domain  # noqa: E402
from resolve import resolve_company  # noqa: E402

TABLE = "parent_child"
DOMAIN_KEYWORDS = ["domain"]
NAME_KEYWORDS = ["company name", "name"]

# Cost guardrail: never send more than this many never-seen companies to Claude
# per upload. Anything beyond the cap is returned as "not in database" instead of
# silently running up a bill. Override with MAX_LLM_LOOKUPS.
MAX_LLM_LOOKUPS = int(os.environ.get("MAX_LLM_LOOKUPS", "50"))
# How many domains to look up per Supabase request (keeps the query URL short).
LOOKUP_CHUNK = 150

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
supabase = (
    create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    if SUPABASE_URL and SUPABASE_SERVICE_KEY
    else None
)


def fetch_known(domains):
    """Fetch known rows for the given normalized domains. Returns {child_domain: row}."""
    known = {}
    unique = sorted({d for d in domains if d})
    for i in range(0, len(unique), LOOKUP_CHUNK):
        chunk = unique[i:i + LOOKUP_CHUNK]
        resp = supabase.table(TABLE).select("*").in_("child_domain", chunk).execute()
        for row in resp.data or []:
            known[row["child_domain"]] = row
    return known


def upsert_finding(record):
    """Persist a newly resolved relationship, keyed by child_domain."""
    supabase.table(TABLE).upsert(record, on_conflict="child_domain").execute()


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/healthz", methods=["GET"])
def healthz():
    return {"ok": supabase is not None}, (200 if supabase else 503)


@app.route("/process", methods=["POST"])
def process():
    if supabase is None:
        flash("Server not configured: SUPABASE_URL / SUPABASE_SERVICE_KEY are missing.")
        return redirect(url_for("index"))

    file = request.files.get("csv_file")
    if not file or file.filename == "":
        flash("Please choose a CSV file.")
        return redirect(url_for("index"))

    reader = csv.DictReader(io.StringIO(file.read().decode("utf-8-sig")))
    rows = list(reader)
    fieldnames = reader.fieldnames or []

    domain_col = find_column(fieldnames, DOMAIN_KEYWORDS)
    if not domain_col:
        flash(f"Could not find a domain column in headers: {fieldnames}")
        return redirect(url_for("index"))
    name_col = find_column(fieldnames, NAME_KEYWORDS)

    # One batched read for everything already in the database (free, no LLM).
    known = fetch_known(normalize_domain(r.get(domain_col, "")) for r in rows)
    out_fields = fieldnames + ["Parent Company Name", "Parent Company Domain", "Verified", "Evidence"]

    # Bring-your-own-key: use the key the user pastes into the form for this upload;
    # fall back to a server-configured key if one is set. Never stored or logged.
    api_key = (request.form.get("api_key") or "").strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key) if api_key else None
    llm_used = 0

    final_rows = []
    for row in rows:
        domain = normalize_domain(row.get(domain_col, ""))
        hit = known.get(domain)
        out = dict(row)
        name = row.get(name_col, "") if name_col else ""

        if hit:
            # Guardrail: a stored "parent" that's just the child's own domain isn't a parent
            # (legacy self-referencing rows) - normalize on read regardless of what's stored.
            if hit.get("parent_domain") and hit["parent_domain"] == domain:
                out["Parent Company Name"] = ""
                out["Parent Company Domain"] = ""
                out["Verified"] = "No"
                out["Evidence"] = no_parent_evidence(name or hit.get("child_name"), hit.get("evidence", ""))
            else:
                out["Parent Company Name"] = hit.get("parent_name") or ""
                out["Parent Company Domain"] = hit.get("parent_domain") or ""
                out["Verified"] = hit.get("verified") or "No"
                out["Evidence"] = hit.get("evidence") or ""
        elif not domain:
            out["Parent Company Name"] = ""
            out["Parent Company Domain"] = ""
            out["Verified"] = "No"
            out["Evidence"] = "No domain provided for this row."
        elif client is None:
            # No API key provided - can't research unknowns, so don't guess.
            out["Parent Company Name"] = ""
            out["Parent Company Domain"] = ""
            out["Verified"] = "No"
            out["Evidence"] = (
                "Not in database. Add an Anthropic API key to resolve companies "
                "that haven't been seen before."
            )
        elif llm_used >= MAX_LLM_LOOKUPS:
            # Cost cap reached - stop calling Claude, don't guess.
            out["Parent Company Name"] = ""
            out["Parent Company Domain"] = ""
            out["Verified"] = "No"
            out["Evidence"] = (
                f"Not in database and per-upload lookup cap ({MAX_LLM_LOOKUPS}) reached - "
                "not researched. Re-run to resolve the remainder."
            )
        else:
            llm_used += 1
            result = resolve_company(client, name, domain)
            out["Parent Company Name"] = result.get("parent_name", "")
            out["Parent Company Domain"] = result.get("parent_domain", "")
            out["Verified"] = result.get("verified", "No")
            out["Evidence"] = result.get("evidence", "")

            verified = out["Verified"].strip().lower()
            record = None
            if verified == "yes":
                parent_domain = normalize_domain(out["Parent Company Domain"])
                if parent_domain:
                    record = {
                        "child_name": name,
                        "child_domain": domain,
                        "parent_name": out["Parent Company Name"],
                        "parent_domain": parent_domain,
                        "verified": "Yes",
                        "evidence": out["Evidence"],
                        "verification_method": "LLM+web search",
                        "date_added": datetime.date.today().isoformat(),
                    }
            elif verified == "no":
                # Cache confirmed "no parent" results too, so we don't re-search them next time.
                record = {
                    "child_name": name,
                    "child_domain": domain,
                    "parent_name": "",
                    "parent_domain": "",
                    "verified": "No",
                    "evidence": out["Evidence"],
                    "verification_method": "LLM+web search",
                    "date_added": datetime.date.today().isoformat(),
                }
            if record:
                upsert_finding(record)
                # Cache in-memory so repeat domains in this same upload don't re-call Claude.
                known[domain] = record

        final_rows.append(out)

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=out_fields)
    w.writeheader()
    w.writerows(final_rows)
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))

    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name="parent-companies-output.csv",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
