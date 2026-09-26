#!/usr/bin/env bash
# Moves an issue to a factory state label, replacing the previous one, and optionally sets its
# size label (replacing the previous size). factory:paused-budget and human:* labels are kept.
#
# Usage: .claude/tools/set-state.sh <issue-number> <factory:state> [S|M|L]
set -euo pipefail
states="factory:triage factory:needs-info factory:awaiting-go factory:ready factory:in-progress factory:in-review factory:changes-requested factory:ready-for-human factory:stuck"
[[ $# -ge 2 && " $states " == *" $2 "* && "${3:-S}" =~ ^[SML]$ ]] ||
  { echo "usage: $0 <issue-number> <one of: $states> [S|M|L]" >&2; exit 1; }
n="$1" state="$2" size="${3:+size:$3}"
current="$(gh api "repos/${FACTORY_REPO:?}/issues/$n/labels" -q '.[].name')"
while read -r label; do
  [[ -z "$label" || "$label" == "$state" || "$label" == "$size" ]] && continue
  if [[ " $states " == *" $label "* || (-n "$size" && "$label" == size:*) ]]; then
    gh api -X DELETE "repos/$FACTORY_REPO/issues/$n/labels/$(jq -rn --arg l "$label" '$l | @uri')" >/dev/null </dev/null
  fi
done <<<"$current"
jq -n --arg s "$state" --arg z "$size" '{labels: ([$s, $z] | map(select(. != "")))}' |
  gh api -X POST "repos/$FACTORY_REPO/issues/$n/labels" --input - >/dev/null
echo "#$n: $state${size:+ $size}"
