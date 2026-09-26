#!/usr/bin/env bash
# Posts a new comment on an issue or PR, with the agent prefix line the factory requires.
# Use it for things the human should be notified about (questions, "ready for review").
#
# Usage: .claude/tools/post-comment.sh <number> <file-with-markdown-body>
set -euo pipefail
[[ $# -eq 2 && -f "$2" ]] || { echo "usage: $0 <number> <body-file>" >&2; exit 1; }
jq -Rs --arg prefix "${FACTORY_AGENT:?}@factory.tobi-braun.com" '{body: ($prefix + "\n\n" + .)}' "$2" |
  gh api -X POST "repos/${FACTORY_REPO:?}/issues/$1/comments" --input - -q .html_url
