# ynab-tools

YNAB balance monitoring and Amazon transaction annotation.

## Architecture

- `src/ynab_tools/core/` — Shared YNAB API client, cache, delta sync, models
- `src/ynab_tools/monitor/` — Balance projection, CC payments, expenses
- `src/ynab_tools/amazon/` — Amazon order scraping, YNAB memo annotation
- `src/ynab_tools/notify/` — Notifiarr + Apprise notifications
- `src/ynab_tools/daemon/` — Unified multi-schedule daemon
- `src/ynab_tools/cli/` — Typer CLI with subcommands
- `src/ynab_tools/config/` — Pydantic v2 settings

## Commands

```bash
uv run pytest tests/ -v --cov          # Run tests
uv run ruff check src/ tests/          # Lint
uv run ruff format src/ tests/         # Format
uv run pyright src/                    # Type check
uv run ynab-tools monitor --dry-run   # Test monitor
uv run ynab-tools amazon --dry-run    # Test amazon
```

## Versioning

ZeroVer (0ver) — major version stays at 0. Bump minor for features, patch for fixes.
Version source: `src/ynab_tools/__init__.py` (read by hatchling).
Release: `git tag v0.x.y && git push --tags` triggers CI to build Docker images and create GitHub release.

## Conventions

- httpx for all HTTP (sync client, respx for tests)
- Pydantic v2 models (not raw dicts)
- Immutable data patterns
- JSON + fcntl file locking for cache (no pickle)
- Loguru for logging
- Typer for CLI

## Docker

Two images built from one repo:
- `ynab-tools` (Dockerfile.amazon) — full unified image with chromium for Amazon scraping (~900MB)
- `ynab-tools-monitor` (Dockerfile.monitor) — lightweight monitor-only image (~50MB)

Production runs the unified image: `ynab-tools daemon` (both monitor + Amazon sync).
