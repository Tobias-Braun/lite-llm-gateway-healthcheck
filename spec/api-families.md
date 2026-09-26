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

For a given round, only the currently configured models of the family count (a model removed from
the configuration no longer affects the family's history). Given the results of those models in a
round:

| Results | Family availability for that round |
|---|---|
| No configured model has a result | `unknown` |
| Every configured model succeeded | `yes` |
| Every configured model failed | `no` |
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
  - `modelname`, `provider`, `company`: as configured.
  - `status`: the model's own latest availability (`yes` / `no` / `unknown`).
  - `lastChecked`, `latencyMs`, `error`: from the model's latest check, or `null` if none yet.
  - `history.availabilityPoints`: the model's own last `history_limit` rounds, oldest first, in
    the same shape as the family's history — independent of the other models in the family.

## Dashboard rendering

- The family panel head shows a status dot and timeline driven by the family's `status` and
  `history`, as today.
- Each row of the model table additionally shows a small availability timeline, in the same style
  as the family's timeline, driven by that model's own `history`.
- `partial` gets its own color, distinct from the existing `yes` (green), `no` (red) and `unknown`
  (gray): a yellow status dot and timeline segment, wherever a `partial` status can appear (today,
  only the family panel head and the family timeline).
