#!/usr/bin/env bash
# Checks the spec against the re-sort thresholds: no file over 300 lines, no folder with more than
# 15 files. Prints each violation and exits 1 if a re-sort is due. Run it from the repo root.
#
# Usage: .claude/tools/spec-check.sh
set -uo pipefail
due=0
while IFS= read -r -d '' file; do
  lines="$(wc -l <"$file" | tr -d ' ')"
  ((lines > 300)) && echo "${file#./}: $lines lines (max 300)" && due=1
done < <(find ./spec -type f -name '*.md' -print0 2>/dev/null)
while IFS= read -r -d '' dir; do
  files="$(find "$dir" -maxdepth 1 -type f | wc -l | tr -d ' ')"
  ((files > 15)) && echo "${dir#./}: $files files (max 15)" && due=1
done < <(find ./spec -type d -print0 2>/dev/null)
exit "$due"
