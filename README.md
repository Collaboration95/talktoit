# tti — talk to your health data

A self-hostable web app for Apple Health users. Drop in your export, ask questions in plain English, and see your data in clean visual templates. No Docker, no database server, no accounts, no cloud.

## What it does

- **Chat** — ask natural-language questions about your health data: "Show my last long run", "Compare my running this month vs last", "How was my resting heart rate this year?"
- **Dashboard** — lightweight Apple Fitness-style panels: activity rings, workout history, steps, resting HR, sleep trends

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node 20 (via nvm: `nvm use 20`)
- A Groq API key (free tier works) or any OpenAI-compatible LLM endpoint

## Quick start

```bash
git clone https://github.com/Collaboration95/talktoit.git
cd tti

# Install tools (one-time)
# macOS: brew install uv
# Or: curl -LsSf https://astral.sh/uv/install.sh | sh

nvm use 20

# Bootstrap
make install

# Set up pre-commit (optional but recommended)
uv tool install pre-commit
pre-commit install

# Configure environment
cp .env.example .env
# Edit .env: set EXPORT_PATH, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

# Ingest your Apple Health export (one-time, ~5-15 min for a full export)
make ingest EXPORT_PATH=/path/to/export.xml

# Run (hot-reload dev mode: backend on :8000, frontend on :5173)
make dev

# Or: build the frontend and serve everything from one port
# make run   # → http://localhost:8000
```

## Development

```bash
make dev       # backend on :8000, frontend on :5173 (hot reload)
make test      # run all tests
make lint      # lint backend + frontend
make typecheck # type check backend + frontend
```

## Configuration (`.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EXPORT_PATH` | for ingest | — | Path to your `export.xml` |
| `LLM_API_KEY` | yes | — | API key for your LLM provider |
| `LLM_BASE_URL` | no | Groq | OpenAI-compatible base URL |
| `LLM_MODEL` | no | `llama-3.3-70b-versatile` | Model name |
| `TTI_DB_PATH` | no | `backend/data/health.duckdb` | Path to the DuckDB file |

## Privacy

Your health data never leaves your machine. The LLM only sees pre-aggregated summaries — never raw records. The database is a local file. No telemetry, no accounts.

## License

MIT
