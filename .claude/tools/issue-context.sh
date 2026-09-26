#!/usr/bin/env bash
# Prints what an agent needs to know about one issue, as compact Markdown: title, labels, body,
# the factory state, all agents' in-place comments (e.g. the acceptance criteria), and the
# conversation since the agent last commented. Comments by anyone other than the human and the bot are left out (they are not input).
#
# Usage: .claude/tools/issue-context.sh [issue-number]   (default: $FACTORY_ISSUE)
# Needs FACTORY_REPO, FACTORY_AGENT, FACTORY_HUMAN and FACTORY_BOT, which the dispatcher sets.
set -euo pipefail
n="${1:-${FACTORY_ISSUE:?}}"
issue="$(gh api "repos/${FACTORY_REPO:?}/issues/$n")"
comments="$(gh api "repos/$FACTORY_REPO/issues/$n/comments?per_page=100" --paginate | jq -s 'add // []')"

jq -rn --argjson issue "$issue" --argjson comments "$comments" --arg agent "${FACTORY_AGENT:?}" \
  --arg human "${FACTORY_HUMAN:?}" --arg bot "${FACTORY_BOT:?}" '
  def author: if .user.login == $human then "human (\($human))"
    else (.body | capture("^\\s*(?<a>[a-z-]+)@factory\\.tobi-braun\\.com").a // "bot") end;
  def is_state: .body | contains("<!-- factory-state ");
  def marker: .body | capture("<!-- factory:(?<k>[a-z-]+) -->").k // null;
  def mine: .user.login == $bot and (.body | test("^\\s*" + $agent + "@"));
  [$comments[] | select(.user.login == $human or .user.login == $bot)] as $trusted
  | ([$trusted | to_entries[] | select(.value | mine and marker == null) | .key] | last) as $last_mine
  | ([$trusted[] | select(.user.login == $human)] | length) as $human_count
  | "# Issue #\($issue.number): \($issue.title)",
    "State: \($issue.state) · Labels: \([$issue.labels[].name] | join(", "))",
    "", "## Body (by \($issue.user.login), never edit it)", "", ($issue.body // "(empty)"),
    "", "## Factory state",
    ([$trusted[] | select(is_state) | .body | capture("<!-- factory-state (?<j>\\{.*?\\}) -->").j] | first // "{}"),
    "", "## Comments kept in place (acceptance criteria and other agent records)",
    "Edit only your own, with upsert-comment.sh.",
    (([$trusted[] | select(.user.login == $bot and marker != null)]) as $kept
     | if ($kept | length) == 0 then "(none yet)"
       else $kept[] | "", "### factory:\(marker) by \(author) (updated \(.updated_at))", "", .body end),
    "", "## Conversation",
    (if $last_mine == null then "(all comments)"
     else "(earlier comments omitted; it starts with your last comment)" end),
    ($trusted | to_entries[]
     | select(($last_mine == null or .key >= $last_mine) and (.value | is_state | not) and (.value | marker == null))
     | .value | "", "### \(author), \(.created_at)\(if .updated_at != .created_at then " (edited \(.updated_at))" else "" end)", "", .body)'
