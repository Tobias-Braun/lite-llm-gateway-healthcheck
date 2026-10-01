#!/bin/bash
# Installs (or with --uninstall removes) the LaunchAgent that starts and stops the stack on a schedule.
set -euo pipefail

LABEL=com.healthcheck.scheduler
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/healthcheck-scheduler.log"
DIR=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$DIR/../.." && pwd)
DOMAIN="gui/$(id -u)"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true

if [[ ${1:-} == --uninstall ]]; then
  rm -f "$PLIST"
  echo "Removed $LABEL (the stack itself is left as is)."
  exit 0
fi

mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
sed -e "s|__REPO__|$REPO|g" -e "s|__LOG__|$LOG|g" "$DIR/$LABEL.plist" > "$PLIST"
plutil -lint -s "$PLIST"
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Installed $LABEL for $REPO, log: $LOG"
