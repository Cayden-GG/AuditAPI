# Repository Guidelines

## Project Structure & Module Organization
- `app/` holds the FastAPI API (`app/main.py`), data models (`app/models.py`), and service modules.
- `app/services/` contains the audit pipeline (sitemap discovery, Lighthouse runs, formatting) and report generation.
- `app/services/reports/sections/` holds individual PDF report sections.
- `app/services/ai/` encapsulates OpenAI request building and schema definitions.
- `audit_results/` is created at runtime by the CLI to store JSON and PDF outputs.

## Build, Test, and Development Commands
- `python -m venv venv` and `source venv/bin/activate` to create/activate a local environment.
- `pip install -r app/services/full_website_performance_audit.egg-info/requires.txt` installs runtime deps (no lockfile yet).
- `uvicorn app.main:app --reload` runs the API locally (FastAPI).
- `python app/services/cli.py --client-name "Acme" --sitemap-url https://example.com/sitemap.xml --only-categories seo,performance --platform desktop --max-urls 50` runs the full audit CLI.

## Coding Style & Naming Conventions
- Python, 4-space indentation, keep functions focused and typed where practical.
- Prefer `snake_case` for functions/variables and `PascalCase` for classes (matches current modules).
- Keep module paths under `app/services/...` aligned with domain (audit, reports, ai).
- No formatter configured; use standard PEP 8 spacing and import ordering.

## Testing Guidelines
- No automated test suite detected; add tests under `tests/` if you introduce new logic.
- Name test files `test_*.py` and mirror module structure for clarity.
- Run tests with `pytest` once a test suite exists.

## Commit & Pull Request Guidelines
- Existing commits are short, descriptive sentences (no enforced convention).
- Use imperative, scoped messages when possible: `add audit config defaults`.
- PRs should include: brief summary, key files touched, and how you validated (commands + results).

## Configuration & Security Notes
- The AI summary uses `dotenv`; define `OPENAI_API_KEY` in a local `.env`.
- Audit output can include client data; avoid committing `audit_results/` or secrets.
