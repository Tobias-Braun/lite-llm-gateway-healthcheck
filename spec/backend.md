# Health-check rounds

How the backend checks configured models and paces gateway requests.

## Round behaviour

On startup, and then every `check_interval_seconds`, the service runs one check round:

- Every model of every configured family is checked: the `healthcheck_prompt` is sent to the
  gateway with a `request_timeout_seconds` timeout.
- A failing or timed-out model is recorded as a failed check with its error message; it never
  aborts the round or blocks other models.
- All models of a round share one `round_id` and timestamp, whether they succeeded or failed.
- Requests are dispatched as concurrent tasks, not run one after another — a slow or timed-out
  model does not delay the rest of the round.

## Request pacing

Sending every model's request at the same instant can trip the gateway's own rate limit, which
shows up as false failures rather than a true outage. To avoid that, the start of consecutive
requests within a round is paced by `request_interval_seconds`:

- The first request starts immediately; each following request starts at least
  `request_interval_seconds` after the previous one started.
- With `request_interval_seconds = 0`, all requests start back-to-back (no pacing) — the
  original, unpaced behaviour.
- Pacing only staggers request *starts*; it does not make requests wait for each other to
  finish, so the concurrency and failure-isolation behaviour above still holds.

## Configuration

| Setting | Env var | Default | Meaning |
|---|---|---|---|
| `check_interval_seconds` | `CHECK_INTERVAL_SECONDS` | `300` | Seconds between the end of one round and the start of the next. |
| `request_timeout_seconds` | `REQUEST_TIMEOUT_SECONDS` | `30` | Per-request timeout against the gateway. |
| `request_interval_seconds` | `REQUEST_INTERVAL_SECONDS` | `2` | Minimum spacing, in seconds, between the start of two consecutive requests within a round (see above). |
| `healthcheck_prompt` | `HEALTHCHECK_PROMPT` | `Reply with OK.` | Prompt sent to every model. |
