# ynab-tools

YNAB balance monitoring and Amazon transaction annotation.

## Features

- **Balance Monitor** — Projects future balances using scheduled transactions, CC payment tracking, and monthly expense averages. Sends alerts via Notifiarr and Apprise.
- **Amazon Sync** — Scrapes Amazon order history and annotates YNAB transactions with item details.
- **Unified Daemon** — Runs both features on configurable schedules with shared rate limiting.

## Usage

```bash
# Install
uv sync

# Run monitor
ynab-tools monitor --dry-run

# Run Amazon sync
ynab-tools amazon --dry-run

# Run daemon
ynab-tools daemon
```

## Configuration

Copy `.env.example` to `.env` and fill in your values. See the example file for all available settings.

## Development

```bash
uv sync --group dev --group test
uv run pytest tests/ -v --cov
uv run ruff check src/ tests/
uv run pyright src/
```
