# ynab-tools

YNAB balance monitoring and Amazon transaction annotation.

## Features

- **Balance Monitor** — Projects future balances using scheduled transactions, CC payment tracking, and monthly expense averages. Sends alerts via Notifiarr and Apprise.
- **Amazon Sync** — Scrapes Amazon order history and annotates YNAB transactions with item details. Sends sync summary via Notifiarr.
- **Unified Daemon** — Runs both features on configurable schedules with shared rate limiting.

## Docker Images

Two images are published to GHCR:

| Image | Description | Size |
|-------|-------------|------|
| `ghcr.io/baker-scripts/ynab-tools` | Full image with Chromium for Amazon scraping + monitor | ~900MB |
| `ghcr.io/baker-scripts/ynab-tools-monitor` | Lightweight monitor-only image | ~50MB |

```bash
# Full image (Amazon sync + monitor)
docker pull ghcr.io/baker-scripts/ynab-tools:latest

# Monitor only
docker pull ghcr.io/baker-scripts/ynab-tools-monitor:latest

# Pin to a version
docker pull ghcr.io/baker-scripts/ynab-tools:0.2.0
```

### Running with Docker

```bash
# Daemon mode (recommended) — runs both monitor and Amazon sync on schedule
docker run -d --name ynab-tools \
  --env-file .env \
  ghcr.io/baker-scripts/ynab-tools:latest \
  ynab-tools daemon --amazon-windows "8-9,19-20"

# Monitor only
docker run -d --name ynab-monitor \
  --env-file .env \
  ghcr.io/baker-scripts/ynab-tools-monitor:latest \
  ynab-tools daemon --monitor-only
```

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
