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

## Co-Authorship

All commits include: `Co-Authored-By: Claude Code <noreply@anthropic.com>`

## Conventions

- httpx for all HTTP (sync client, respx for tests)
- Pydantic v2 models (not raw dicts)
- Immutable data patterns
- JSON + fcntl file locking for cache (no pickle)
- Loguru for logging
- Typer for CLI
