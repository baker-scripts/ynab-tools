# RCA: Double-Counted Credit Card Transfers

**Date:** 2026-03-22
**Severity:** Critical (incorrect balance projections, misleading notifications)
**Status:** Fixed

## Summary

The balance projection was counting every CC payment transfer **twice**, because YNAB's API returns both sides of a scheduled transfer and `expand_scheduled_transactions()` processed both.

## Impact

- Projected checking balance dropped 2x the actual CC payment amount for every CC with a scheduled transfer
- Notifications showed duplicate transfer entries (e.g., "Transfer : Chase" appearing twice)
- Misleading balance alerts — projected minimums were far lower than reality
- User confusion led to investigating/creating manual transfers in YNAB

## Root Cause

YNAB's `/scheduled_transactions` API returns **both sides** of every transfer:

| Side | account_id | transfer_account_id | amount |
|------|-----------|---------------------|--------|
| Checking | DG Checking | Chase CC | -$500 (outflow) |
| CC | Chase CC | DG Checking | +$500 (inflow) |

In `scheduler.py:expand_scheduled_transactions()`, the filter logic accepted both:

```python
on_checking = acct_id in account_set      # True for checking side
xfer_to_checking = xfer_id in account_set  # True for CC side
if not on_checking and not xfer_to_checking:
    continue  # Both pass!
```

The amount normalization then produced identical outflows from both:
- Checking side: `amount = raw_amount = -500.0`
- CC side: `amount = -raw_amount = -(+500.0) = -500.0`

Both were added to the projection, doubling the impact.

## Why It Wasn't Caught

The test suite tested each side **in isolation** (`test_on_checking`, `test_transfer_to_checking`), never together as YNAB actually returns them. No integration test simulated realistic dual-sided transfer data.

## Fix

Added early return in `expand_scheduled_transactions()` to skip the non-monitored side of transfers:

```python
if xfer_to_checking and not on_checking:
    continue
```

This ensures only the checking-side entry (which has the correct sign natively) is processed.

## Separate Issue: $0 Scheduled Transfers

The tool does **not** create scheduled transactions (no POST to YNAB scheduled_transactions endpoint). The `ynab_cc_create_payments` config exists but is unused in logic. $0 scheduled transfers in YNAB were created manually and need manual cleanup.

## Prevention

- Added `test_both_sides_of_transfer_not_double_counted` — tests realistic YNAB data with both sides of a transfer
- Added `test_inbound_transfer_both_sides_not_double_counted` — same for inbound transfers
- Updated `test_transfer_to_checking` → `test_cc_side_only_transfer_skipped` to reflect new behavior

## Files Changed

- `src/ynab_tools/monitor/scheduler.py` — skip CC-side of transfers
- `tests/monitor/test_scheduler.py` — 3 tests added/updated
