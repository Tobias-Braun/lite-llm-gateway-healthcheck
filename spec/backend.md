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
| `fake_data` | `FAKE_DATA` | `false` | Dev mode: generate synthetic results instead of calling the gateway (see below). |

## Fake data mode

With `fake_data` on, the service never calls the gateway — `gateway_url` and `api_key` stay
required settings but go unused — so the dashboard can be tried without a real gateway or API
key.

### Synthetic rounds

Each round (startup and every `check_interval_seconds`, same as normal mode) still produces one
shared `round_id`/timestamp result per model of every configured family, but each model's result
is generated instead of requested from the gateway:

- 90% chance of success: a random latency between 50 and 400 ms (inclusive), no error.
- 10% chance of failure: no latency, error message `Simulated failure (fake data mode)`.

Every other round rule (concurrency, failure isolation, request pacing) is not applicable, since
no HTTP requests are made.

### Startup backfill

On startup, before the first round runs, each currently configured model that has fewer than 48
stored rounds is backfilled with synthetic rounds so its history starts populated instead of
empty:

- For such a model, enough backdated rounds are inserted to bring its stored round count to 48,
  generated the same way as a normal synthetic round (see above).
- Backfilled rounds are spaced `check_interval_seconds` apart, oldest first, ending immediately
  before the model's oldest existing stored round, or immediately before startup time if it has
  none yet.
- A model that already has 48 or more stored rounds is left alone: no rounds are added for it on
  this or any later restart.
- Backfilled rounds for different models that land on the same timestamp share one round_id, the
  same as a normal round; a model needing fewer backfilled rounds than others simply has no row
  for the older timestamps it doesn't need.

After the backfill, the normal round loop starts and keeps appending further synthetic rounds the
same way, so history keeps moving as it would in real mode.
