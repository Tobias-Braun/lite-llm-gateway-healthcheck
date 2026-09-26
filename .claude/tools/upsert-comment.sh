#!/usr/bin/env bash
# Creates or edits in place the agent's comment with the given key, e.g. the requirements agent's
# acceptance criteria (key "requirements"). There is at most one such comment per issue and key;
# it carries the agent prefix and a hidden `<!-- factory:<key> -->` marker. Editing doesn't notify
# anyone, so pair a meaningful change with a short post-comment.sh note.
#
# Usage: .claude/tools/upsert-comment.sh <number> <key> <file-with-markdown-body>
set -euo pipefail
[[ $# -eq 3 && -f "$3" && "$2" =~ ^[a-z-]+$ ]] || { echo "usage: $0 <number> <key> <body-file>" >&2; exit 1; }
n="$1" key="$2"
id="$(gh api "repos/${FACTORY_REPO:?}/issues/$n/comments?per_page=100" --paginate | jq -rs \
  --arg bot "${FACTORY_BOT:?}" --arg marker "<!-- factory:$key -->" \
  '[add[]? | select(.user.login == $bot and (.body | contains($marker)))] | first | .id // empty')"
body="$(jq -Rs --arg prefix "${FACTORY_AGENT:?}@factory.tobi-braun.com" --arg marker "<!-- factory:$key -->" \
  '{body: ($prefix + "\n" + $marker + "\n\n" + .)}' "$3")"
if [[ -n "$id" ]]; then
  gh api -X PATCH "repos/$FACTORY_REPO/issues/comments/$id" --input - -q .html_url <<<"$body"
else
  gh api -X POST "repos/$FACTORY_REPO/issues/$n/comments" --input - -q .html_url <<<"$body"
fi
