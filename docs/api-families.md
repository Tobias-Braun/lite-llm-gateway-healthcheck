# Family and model availability

Contract for `GET /api/families` and how the dashboard renders it.

## Availability values

| Value | Meaning |
|---|---|
| `yes` | Available. |
| `no` | Unavailable. |
| `partial` | Family-only: some but not all of its models were available. |
| `unknown` | No check result yet. |

A single model's `status` and history points are always `yes`, `no` or `unknown` — a model either
answered a check or it didn't. `partial` only appears at family level, where it aggregates several
models.

## Family aggregation

Families and models come from the stored model list (see `docs/backend.md`, "Model list"); only
its active models are returned. For a given round, only the active models of the family count (a
model that became inactive no longer affects the family's history). Given the results of those models in a
round:

| Results | Family availability for that round |
|---|---|
| No active model has a result | `unknown` |
| Every active model succeeded | `yes` |
| Every active model failed | `no` |
| Some succeeded, some failed | `partial` |

This rule produces both the family's `status` field (the latest round) and every point of
`history.availabilityPoints`.

## Response shape

`GET /api/families` returns a list of families, each with:

- `title`: family name.
- `status`: the family's availability for its latest round (see above).
- `history.availabilityPoints`: the family's last `history_limit` rounds, oldest first, each an
  `{ datetime, available }` pair.
- `models`: the family's models, each with:
  - `modelname`, `provider`, `company`: from the stored model list.
  - `status`: the model's own latest availability (`yes` / `no` / `unknown`).
  - `lastChecked`, `latencyMs`, `error`: from the model's latest check, or `null` if none yet.
  - `history.availabilityPoints`: the model's own last `model_history_limit` rounds, oldest
    first, in the same shape as the family's history — independent of the other models in the
    family, and of the family's own `history_limit` window. Each point additionally carries
    `latencyMs`/`error` from that round's stored check result for this model: present (one of
    them non-null) when the round has a result, `null`/absent when the point's `available` is
    `unknown`. Family-level `history.availabilityPoints` keep the plain `{ datetime, available }`
    shape — a family round aggregates several models, so a single latency or error wouldn't mean
    anything there.

## Dashboard rendering

- The family panel head shows a status dot and timeline driven by the family's `status` and
  `history`, as today. Its tooltips (status dot and timeline segments) show only time and status,
  never latency or error — a family round aggregates several models.
- Each row of the model table additionally shows a small availability timeline, in the same style
  as the family's timeline, driven by that model's own `history`. Because `model_history_limit`
  differs from the family's `history_limit`, the model table carries a visible note (e.g. a
  tooltip on the timeline column's header) that this timeline covers a different, more recent
  time window than the family timeline above it, so the two aren't read as the same range.
- `partial` gets its own color, distinct from the existing `yes` (green), `no` (red) and `unknown`
  (gray): a yellow status dot and timeline segment, wherever a `partial` status can appear (today,
  only the family panel head and the family timeline).
- Each model row also shows two columns:
  - **Latency**: the model's latest check latency (its `latencyMs`), e.g. `120 ms`. Shows `—` if
    the model has no check yet or its latest check failed.
  - **Uptime**: the success rate over the model's shown history window, as `yes / (yes + no)`
    rounds of `history.availabilityPoints`, rounded to a whole-number percentage (e.g. `98%`).
    `unknown` rounds count towards neither side. Shows `—` if every round in the window is
    `unknown`.
- Hovering a model's history-timeline cell shows the same time and status as today, plus — only
  when that round has a result — the latency in ms for a `yes` round or the error text for a `no`
  round. `unknown` cells are unchanged (time and status only).
