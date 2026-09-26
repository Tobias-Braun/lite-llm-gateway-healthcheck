#!/usr/bin/env bash
# Prints what the implementer needs to fix its PR, as compact Markdown: the PR, the result of every
# check on its head commit (with the summary of failed ones), the review agent's latest verdict, and
# the human's reviews, inline comments and PR comments since the last push. Prints "No open PR" if
# the issue branch has none yet.
#
# Usage: .claude/tools/pr-context.sh
# Needs FACTORY_REPO, FACTORY_BRANCH and FACTORY_HUMAN, which the dispatcher sets.
set -euo pipefail
repo="${FACTORY_REPO:?}"
pr="$(gh api "repos/$repo/pulls?head=${repo%%/*}:${FACTORY_BRANCH:?}&state=open" -q '.[0] // empty')"
[[ -n "$pr" ]] || { echo "No open PR from $FACTORY_BRANCH yet."; exit 0; }
n="$(jq -r .number <<<"$pr")"
sha="$(jq -r .head.sha <<<"$pr")"
pushed="$(gh api "repos/$repo/commits/$sha" -q .commit.committer.date)"

jq -rn --argjson pr "$pr" --arg pushed "$pushed" --arg human "${FACTORY_HUMAN:?}" \
  --argjson runs "$(gh api "repos/$repo/commits/$sha/check-runs" -q .check_runs)" \
  --argjson statuses "$(gh api "repos/$repo/commits/$sha/status" -q .statuses)" \
  --argjson reviews "$(gh api "repos/$repo/pulls/$n/reviews?per_page=100" --paginate | jq -s 'add // []')" \
  --argjson inline "$(gh api "repos/$repo/pulls/$n/comments?per_page=100" --paginate | jq -s 'add // []')" \
  --argjson comments "$(gh api "repos/$repo/issues/$n/comments?per_page=100" --paginate | jq -s 'add // []')" '
  def since: select((.submitted_at // .created_at) > $pushed);
  "# PR #\($pr.number): \($pr.title)",
  "Head: \($pr.head.sha[0:7]), pushed \($pushed)",
  "", "## Checks on the head commit",
  (if ($runs + $statuses | length) == 0 then "(none)" else empty end),
  ($runs[] | "- \(.name): \(.conclusion // .status)"
    + (if .conclusion == "failure" then "\n  \(.output.title // "")\n  \((.output.summary // "")[0:1500])" else "" end)),
  ($statuses[] | "- \(.context): \(.state)\(if .description then " (\(.description))" else "" end)"),
  "", "## Latest review agent verdict",
  ([$comments[] | select(.body | contains("<!-- factory:review -->"))] | last
   | if . == null then "(none yet)" else "(\(.created_at))", "", .body end),
  "", "## The human since the last push",
  ([($reviews[] | select(.user.login == $human) | since
      | "### Review: \(.state), \(.submitted_at)\n\n\(.body // "")"),
    ($inline[] | select(.user.login == $human) | since
      | "### On \(.path):\(.line // .original_line), \(.created_at)\n\n\(.body)"),
    ($comments[] | select(.user.login == $human) | since
      | "### Comment, \(.created_at)\n\n\(.body)")]
   | if length == 0 then "(nothing)" else .[] end)'
