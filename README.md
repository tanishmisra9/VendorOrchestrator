# Agentic Vendor Master Assistant

A modular Agentic AI solution that manages, cleans, deduplicates, and enriches vendor data across an enterprise. Built with LangGraph orchestration, OpenAI GPT-4, and a Streamlit analyst UI.

**Live demo:** [vendororchestrator-production.up.railway.app](https://vendororchestrator-production.up.railway.app)

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
- **Input validation** on the Add Vendor form (EIN format tax ID, 5-digit ZIP, 2-letter state code)
- **Password authentication** gate (optional, via environment variable)
- **Alembic database migrations** for safe schema evolution
- **Upload size limit** (200 MB default) to prevent OOM on large files
- **Sanitized error messages** — API keys, credentials, and connection strings are stripped from UI error displays
- **Resilient entrypoint** — retries database migrations up to 10 times on startup, handling cold-start race conditions on cloud platforms

## Deployment

The app is deployed on [Railway](https://railway.app) with two services:

- **VendorOrchestrator** — Dockerized Streamlit app built from this repo
- **MySQL** — Railway-managed MySQL 8.0 instance

Railway auto-deploys on every push to `master`. The entrypoint script waits for the database to be ready, runs Alembic migrations, then starts Streamlit on the Railway-assigned `PORT`.

### Deploy your own

1. Push this repo to GitHub
2. Create a new project on [Railway](https://railway.app)
3. Add a **MySQL** database service
4. Add a new service from your GitHub repo
5. Set environment variables on the app service (copy `MYSQLHOST`, `MYSQLPORT`, `MYSQLUSER`, `MYSQLPASSWORD`, `MYSQLDATABASE` from the MySQL service into `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`)
6. Add your `OPENAI_API_KEY`
7. Under **Settings > Networking**, generate a domain and set the port to match Railway's `PORT` (typically `8080`)

## Quick start (local)

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

On startup, the entrypoint script retries Alembic migrations until the database is ready, then starts the app.

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

In Docker and Railway, migrations run automatically on container startup via `entrypoint.sh`.

## Project structure

```
agents/          Agent modules (DataQuality, Deduplication, Loader, VendorCheck)
alembic/         Database migration scripts (Alembic)
context/         MCP shared context layer (in-memory state per pipeline run)
db/              SQLAlchemy models and connection factory with retry logic
orchestrator/    LangGraph StateGraph workflow with stepwise execution
ui/              Streamlit analyst interface with custom CSS theming
utils/           Fuzzy matching, audit logging, error sanitization, LIKE escaping
tests/           Unit tests for agents, matching, loader, and hardening
data/            Sample vendor CSVs (100k well-formed, 50k malformed for testing)
entrypoint.sh    Startup script with database readiness retry loop
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

51 tests covering agents, matching logic, loader behavior, error sanitization, LIKE escaping, deterministic canonical selection, and prompt injection sanitization.

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

## Tech stack

- **Python 3.11** — runtime
- **LangGraph** — agent orchestration
- **OpenAI GPT-4** — LLM for ambiguous deduplication and vendor checks
- **Streamlit** — analyst UI
- **MySQL 8.0** — vendor master database
- **SQLAlchemy** — ORM
- **Alembic** — database migrations
- **RapidFuzz** — fuzzy string matching
- **Docker** — containerization
- **Railway** — cloud deployment
