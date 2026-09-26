#!/usr/bin/env bash
# Prints everything the reviewer gets, and nothing more: the PR, the checks on its head commit, the
# acceptance criteria and the spec change recorded on the issue, and the diff against main
# (lockfiles left out). The reviewer reads the spec files the diff touches itself.
#
# Usage: .claude/tools/review-context.sh   (run from the repo root, on the issue branch)
# Needs FACTORY_REPO, FACTORY_ISSUE, FACTORY_BRANCH and FACTORY_BOT, which the dispatcher sets.
set -euo pipefail
repo="${FACTORY_REPO:?}"
pr="$(gh api "repos/$repo/pulls?head=${repo%%/*}:${FACTORY_BRANCH:?}&state=open" -q '.[0] // empty')"
[[ -n "$pr" ]] || { echo "No open PR from $FACTORY_BRANCH: nothing to review."; exit 1; }
sha="$(jq -r .head.sha <<<"$pr")"
[[ "$(git rev-parse HEAD)" == "$sha" ]] ||
  { echo "The checkout isn't the PR's head commit ${sha:0:7}; run: git fetch origin && git checkout --detach $sha" >&2; exit 1; }
comments="$(gh api "repos/$repo/issues/${FACTORY_ISSUE:?}/comments?per_page=100" --paginate | jq -s 'add // []')"

jq -rn --argjson pr "$pr" --argjson comments "$comments" --arg bot "${FACTORY_BOT:?}" \
  --argjson runs "$(gh api "repos/$repo/commits/$sha/check-runs" -q .check_runs)" \
  --argjson statuses "$(gh api "repos/$repo/commits/$sha/status" -q .statuses)" '
  def kept($key): [$comments[] | select(.user.login == $bot and (.body | contains("<!-- factory:\($key) -->")))]
    | first | .body // "(missing)";
  "# PR #\($pr.number): \($pr.title) (head \($pr.head.sha[0:7]))", "", ($pr.body // ""),
  "", "## Checks on the head commit",
  (if ($runs + [$statuses[] | select(.context != "factory/review")] | length) == 0 then "(none)" else empty end),
  ($runs[] | "- \(.name): \(.conclusion // .status)"),
  ($statuses[] | select(.context != "factory/review") | "- \(.context): \(.state)"),
  "", "## Acceptance criteria (requirements agent)", "", kept("requirements"),
  "", "## Spec change (spec agent)", "", kept("spec")'
echo
echo "## Diff against main"
echo
git diff --stat origin/main...HEAD -- . ':(exclude)*.lock' ':(exclude)*-lock.json' ':(exclude)*.sum'
echo
git diff origin/main...HEAD -- . ':(exclude)*.lock' ':(exclude)*-lock.json' ':(exclude)*.sum'
