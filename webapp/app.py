import csv
import datetime
import io
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, send_file, url_for

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = BASE_DIR / "parent-child-skill"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from lib import find_column, no_parent_evidence, normalize_domain  # noqa: E402
from resolve import resolve_company  # noqa: E402

DB_PATH = SKILL_DIR / "data" / "known-parent-child.csv"
DB_FIELDS = [
    "child_name", "child_domain", "parent_name", "parent_domain",
    "verified", "evidence", "verification_method", "date_added",
]
DOMAIN_KEYWORDS = ["domain"]
NAME_KEYWORDS = ["company name", "name"]

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")


def load_known_db():
    known = {}
    with open(DB_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            known[row["child_domain"]] = row
    return known


def save_known_db(known):
    with open(DB_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DB_FIELDS)
        w.writeheader()
        for rec in sorted(known.values(), key=lambda r: r["child_domain"]):
            w.writerow(rec)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
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

    known = load_known_db()
    out_fields = fieldnames + ["Parent Company Name", "Parent Company Domain", "Verified", "Evidence"]

    client = anthropic.Anthropic()

    final_rows = []
    for row in rows:
        domain = normalize_domain(row.get(domain_col, ""))
        hit = known.get(domain)
        out = dict(row)

        name = row.get(name_col, "") if name_col else ""

        if hit:
            # Guardrail: a stored "parent" that's just the child's own domain isn't a parent
            # (legacy self-referencing rows) - normalize on read regardless of what's stored.
            if hit["parent_domain"] and hit["parent_domain"] == domain:
                out["Parent Company Name"] = ""
                out["Parent Company Domain"] = ""
                out["Verified"] = "No"
                out["Evidence"] = no_parent_evidence(name or hit.get("child_name"), hit["evidence"])
            else:
                out["Parent Company Name"] = hit["parent_name"]
                out["Parent Company Domain"] = hit["parent_domain"]
                out["Verified"] = hit["verified"]
                out["Evidence"] = hit["evidence"]
        else:
            result = resolve_company(client, name, domain)
            out["Parent Company Name"] = result.get("parent_name", "")
            out["Parent Company Domain"] = result.get("parent_domain", "")
            out["Verified"] = result.get("verified", "No")
            out["Evidence"] = result.get("evidence", "")

            verified = out["Verified"].strip().lower()
            if verified == "yes":
                parent_domain = normalize_domain(out["Parent Company Domain"])
                if domain and parent_domain and domain not in known:
                    known[domain] = {
                        "child_name": name,
                        "child_domain": domain,
                        "parent_name": out["Parent Company Name"],
                        "parent_domain": parent_domain,
                        "verified": "Yes",
                        "evidence": out["Evidence"],
                        "verification_method": "LLM+web search",
                        "date_added": datetime.date.today().isoformat(),
                    }
            elif verified == "no" and domain and domain not in known:
                # Cache confirmed "no parent" results too, so we don't re-search them next time.
                known[domain] = {
                    "child_name": name,
                    "child_domain": domain,
                    "parent_name": "",
                    "parent_domain": "",
                    "verified": "No",
                    "evidence": out["Evidence"],
                    "verification_method": "LLM+web search",
                    "date_added": datetime.date.today().isoformat(),
                }

        final_rows.append(out)

    save_known_db(known)

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
