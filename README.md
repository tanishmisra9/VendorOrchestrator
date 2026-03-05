# Agentic Vendor Master Assistant

A modular Agentic AI solution that manages, cleans, deduplicates, and enriches vendor data across an enterprise. Built with LangGraph orchestration, OpenAI GPT-4, and a Streamlit analyst UI.

## Architecture

The system distributes work across four autonomous agents coordinated via a shared MCP (Model Context Protocol) context layer:

- **DataQualityAgent** — Standardizes vendor names, addresses, and tax IDs; flags records with quality issues
- **DeduplicationAgent** — Clusters duplicates using blocking strategies, RapidFuzz fuzzy matching, and LLM-based reasoning for ambiguous cases
- **LoaderAgent** — Bulk-loads deduplicated records into the MySQL vendor master with canonical/duplicate status
- **VendorCheckAgent** — Real-time duplicate check when analysts add new vendors manually

### Key features

- **Batch pipeline** with live progress bar and typewriter status animation
- **Column validation** on upload with visual green/red pill indicators for matched, missing, and extra columns
- **Blocking-based deduplication** for scalable matching (tested at 100k records) — exact tax ID matching, multi-strategy blocking (sorted tokens, first token, tax ID), and a name-similarity override for near-identical vendor names
- **LLM fail-fast** — gracefully degrades if OpenAI quota is exhausted (2 consecutive failures skips remaining LLM calls)
- **LLM prompt injection protection** — vendor field sanitization (truncation, control char stripping) and system-message guardrails
- **Search vendor master** with aggregate metrics, default active-vendor preview, LIKE-injection-safe search, and expandable duplicate cluster views
- **Audit log** tracking all agent actions and analyst override decisions, with configurable strict mode
- **Input validation** on the Add Vendor form (EIN format tax ID, 5/9-digit ZIP, 2-letter state code)
- **Password authentication** gate (optional, via environment variable)
- **Alembic database migrations** for safe schema evolution
- **Upload size limit** (200 MB default) to prevent OOM on large files
- **Sanitized error messages** — API keys, credentials, and connection strings are stripped from UI error displays

## Quick start

### Prerequisites

- Docker & Docker Compose
- OpenAI API key

### Run with Docker

```bash
cp .env.example .env
# Edit .env with your OpenAI API key

docker compose up --build
```

The Streamlit UI will be available at `http://localhost:8501`.

On startup, Alembic runs `upgrade head` to apply any pending database migrations before the app starts.

### Run locally (development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — ensure MySQL is running locally with matching credentials

# Apply database migrations
alembic upgrade head

streamlit run ui/app.py
```

## Database migrations

Schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/). When you modify `db/models.py`:

```bash
# Auto-generate a migration
alembic revision --autogenerate -m "describe your change"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

In Docker, migrations run automatically on container startup.

## Project structure

```
agents/          Agent modules (DataQuality, Deduplication, Loader, VendorCheck)
alembic/         Database migration scripts (Alembic)
context/         MCP shared context layer (in-memory state per pipeline run)
db/              MySQL schema (init.sql), SQLAlchemy models, connection factory
orchestrator/    LangGraph StateGraph workflow with stepwise execution
ui/              Streamlit analyst interface
utils/           Fuzzy matching, audit logging, error sanitization, LIKE escaping
tests/           Unit tests for agents, matching, and loader
data/            Sample vendor CSVs (100k well-formed, 50k malformed for testing)
```

## Usage

1. **Batch pipeline** — Upload a CSV/XLSX vendor file (max 200 MB). Column validation runs immediately, showing which expected columns are present or missing. The pipeline then runs DataQuality → Deduplication → Loader with a live progress bar.
2. **Add vendor** — Enter a single vendor record with validated fields (EIN tax ID, 5-digit ZIP, 2-letter state). The VendorCheckAgent checks for duplicates before insertion, with an option to override and force-add.
3. **Search vendors** — Browse the vendor master with aggregate metrics (active, total, duplicates). Expand any vendor to see its duplicate cluster. Toggle to include duplicate records in results.
4. **Audit log** — Review all agent actions and analyst override decisions with filtering by agent.

## Authentication

Set `REQUIRE_AUTH=true` and `APP_PASSWORD=your-secret` in `.env` to enable a password gate. For production, deploy behind an OAuth2 proxy (e.g., OAuth2-proxy, Cloudflare Access).

## Sample data

Two sample files are included in `data/` for testing:

- `sample_vendors_100k.csv` — 100,000 records with realistic duplicates, name variations, and data quality issues
- `sample_vendors_malformed_50k.csv` — 50,000 records with missing required columns, extra columns, and internal data issues (for testing column validation)

## Testing

```bash
pytest tests/ -v
```

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key for LLM deduplication | (required) |
| `MYSQL_HOST` | MySQL hostname | `localhost` |
| `MYSQL_PORT` | MySQL port | `3306` |
| `MYSQL_USER` | MySQL user | `vendor_admin` |
| `MYSQL_PASSWORD` | MySQL password | `changeme` |
| `MYSQL_DATABASE` | MySQL database name | `vendor_master_db` |
| `REQUIRE_AUTH` | Enable password authentication gate | `false` |
| `APP_PASSWORD` | Password for authentication gate | (empty) |
| `STRICT_AUDIT` | Fail pipeline on audit write errors | `true` |
