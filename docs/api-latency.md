# Latency history

Contract for `GET /api/latency` and how the dashboard renders it.

## Request

| Parameter | Default | Meaning |
|---|---|---|
| `span` | `live` | `live`, `hour` (hour of day), `weekday` (day of week) or `monthday` (day of month). |
| `days` | `30` | Lookback for aggregate spans, 1–365. Ignored for `live`. |
| `tz` | `UTC` | IANA time zone the aggregate buckets are computed in. |
| `family` | — | Family title. Omitted: one series per active family (the overview). |
| `model` | — | Model name within `family`; requires `family`. |

Invalid `span`, `days` or `tz`, or `model` without `family` → 422. A family or model that is not
in the active model list → 404.

## Response

`{ span, series }`, one series per requested family/model, each with:

- `family`, `model` (`null` for a family series).
- `points` (live only, else `null`): the last `history_limit` rounds, oldest first, each
  `{ datetime, available, latencyMs, error }`.
  - Model series: that round's own availability (`yes`/`no`), latency and error — the same
    window length as the family timeline, not the shorter `model_history_limit`.
  - Family series: the family availability (see `docs/api-families.md`) and the mean latency of the
    round's successful active models (`null` if none succeeded); `error` is always `null`.
- `buckets` (aggregate spans only, else `null`): every bucket of the span — hours `0`–`23`,
  weekdays `0`–`6` (Monday = 0) or days `1`–`31` — each `{ bucket, avgMs, p95Ms, count }`.
  Every successful check of the series' models within the last `days` days is placed into the
  bucket of its round time in `tz`. Empty buckets have `count = 0` and `null` figures.
- `summary`: `{ avgMs, p95Ms, count }` over the individual successful checks behind the series
  (the shown live rounds, or the lookback window).

Only successful checks carry a latency; failures never count towards any figure. Averages are
arithmetic means, p95 is nearest-rank; both are rounded to whole milliseconds.

## Dashboard rendering

- Latency is drawn as line charts (d3) in purple (`--latency`); missing values leave a gap.
  Hovering shows the time or bucket and the latency (aggregates: avg, p95 and check count).
- Every chart has a span switch (Live / Hour of day / Day of week / Day of month) and, for
  aggregates, a lookback of 7 / 30 / 90 days. Aggregates use the viewer's browser time zone.
  Live charts refresh with the dashboard; the selection is per chart.
- **Latency overview** (above the families): one line per family in its own color, plus a table
  of each family's `summary` (avg, p95, checks).
- **Family latency**: inside an open family panel, above the model table; only fetched while the
  panel is open.
- **Model detail**: clicking a model name expands a full-width row below it with the model's
  health bar over the family-length window (from the live `points`) and its own latency chart.
  Expanded rows stay open across refreshes.
