#!/usr/bin/env bash
# Records the review agent's verdict on the issue's PR: a new PR comment with the findings (agent
# prefix and a `<!-- factory:review -->` marker, so the implementer finds it) and the commit status
# `factory/review` on the head commit, which branch protection requires. The bot can't approve its
# own PR, so this status is the approval. Only the review agent may run it, and only for the commit
# it reviewed: if the PR moved on, the verdict is refused.
#
# Usage: .claude/tools/set-review.sh <success|failure> <file-with-markdown-findings>
set -euo pipefail
[[ $# -eq 2 && "$1" =~ ^(success|failure)$ && -f "$2" ]] || { echo "usage: $0 <success|failure> <body-file>" >&2; exit 1; }
[[ "${FACTORY_AGENT:-}" == review-agent ]] || { echo "only the review agent sets factory/review" >&2; exit 1; }
verdict="$1" repo="${FACTORY_REPO:?}"
pr="$(gh api "repos/$repo/pulls?head=${repo%%/*}:${FACTORY_BRANCH:?}&state=open" -q '.[0] // empty')"
[[ -n "$pr" ]] || { echo "No open PR from $FACTORY_BRANCH." >&2; exit 1; }
n="$(jq -r .number <<<"$pr")" sha="$(jq -r .head.sha <<<"$pr")"
[[ "$(git rev-parse HEAD)" == "$sha" ]] || { echo "The PR moved on to ${sha:0:7} since you checked it out; review that commit instead." >&2; exit 1; }

title="Approved"
[[ "$verdict" == failure ]] && title="Changes requested"
url="$(jq -Rs --arg prefix "review-agent@factory.tobi-braun.com" --arg title "$title" --arg sha "${sha:0:7}" \
  '{body: ($prefix + "\n<!-- factory:review -->\n\n## " + $title + " (" + $sha + ")\n\n" + .)}' "$2" |
  gh api -X POST "repos/$repo/issues/$n/comments" --input - -q .html_url)"
jq -n --arg state "$verdict" --arg url "$url" --arg d "$title by the review agent" \
  '{state: $state, context: "factory/review", description: $d, target_url: $url}' |
  gh api -X POST "repos/$repo/statuses/$sha" --input - >/dev/null
echo "PR #$n at ${sha:0:7}: factory/review = $verdict ($url)"
