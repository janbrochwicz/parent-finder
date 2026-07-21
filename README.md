# Workflows.io-Hackathon

Parent-Child company finder: upload a CSV of company domains, get each company's
parent/owning company back.

## How it works

1. **Database first (free).** Every domain is looked up in a Supabase Postgres
   table of ~3,560 known relationships. Hits return instantly, no LLM, no cost.
2. **LLM fallback (only for unknowns).** Companies not in the database are
   resolved with Claude + web search, and confirmed results are written back so
   the database grows and the same company is never looked up twice.

Two ways to run it:

- **`parent-child-skill/`** — the original Claude Code skill (local CSV database).
  See `parent-child-skill/SKILL.md`.
- **`webapp/`** — the hosted web app (Supabase-backed database). This is what gets
  deployed.

## Web app

### Local development

```bash
cd webapp
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in SUPABASE_SERVICE_KEY and ANTHROPIC_API_KEY
python app.py               # http://localhost:5001
```

### Environment variables

| Var | What it is |
|---|---|
| `SUPABASE_URL` | Project URL (already set for the hackathon project) |
| `SUPABASE_SERVICE_KEY` | Supabase service_role key. Server-side only, never commit. |
| `ANTHROPIC_API_KEY` | Only used for companies not already in the database |
| `FLASK_SECRET_KEY` | Any random string (session signing) |
| `MAX_LLM_LOOKUPS` | Cost cap: max never-seen companies sent to Claude per upload (default 50; deploy sets 25) |

### Deploy to DigitalOcean

The app is containerized (`Dockerfile`) and deploys on DigitalOcean App Platform
via `.do/app.yaml`.

```bash
doctl apps create --spec .do/app.yaml
```

Then set the three secrets (`SUPABASE_SERVICE_KEY`, `ANTHROPIC_API_KEY`,
`FLASK_SECRET_KEY`) in the DO dashboard under the app's Settings, or in the spec
before creating. Health check is at `/healthz`.

## Data / backend

- **Supabase project:** `parent-finder-hackathon`
- **Table:** `public.parent_child` (`child_domain` primary key). Row Level Security
  is on with no policies — only the server (service_role key) can read/write it.
- Seeded from `parent-child-skill/data/known-parent-child.csv`.
