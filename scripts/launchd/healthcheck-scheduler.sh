#!/bin/bash
# Keeps the Docker Compose stack running during the day and only while online.
#
# Run by launchd at login and every few minutes (see com.healthcheck.scheduler.plist). Instead of
# reacting to start/stop events, every run derives the desired state from the current local time
# and connectivity and applies it, so runs missed during sleep, timezone changes while traveling
# and connection drops are all handled by the next run. Both compose commands are idempotent.
set -u

START_HOUR=${START_HOUR:-7}
STOP_HOUR=${STOP_HOUR:-22}
# Apple's captive portal check: answers "Success" only with real internet access, so hotel or
# train Wi-Fi login pages count as offline too.
PROBE_URL=${PROBE_URL:-http://captive.apple.com/hotspot-detect.html}

# launchd starts jobs with a minimal PATH; add the usual Docker CLI locations (Rancher Desktop, Homebrew).
export PATH="$HOME/.rd/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

REPO=$(cd "$(dirname "$0")/../.." && pwd)
compose() { docker compose -f "$REPO/docker-compose.yml" "$@"; }
log() { echo "$(date '+%Y-%m-%d %H:%M:%S %Z') $*"; }

# 10#: hours like "08" would otherwise be parsed as invalid octal.
hour=$((10#$(date +%H)))
if (( hour < START_HOUR || hour >= STOP_HOUR )); then
  desired=down reason="outside ${START_HOUR}:00-${STOP_HOUR}:00"
elif ! curl -fsS --max-time 5 "$PROBE_URL" 2>/dev/null | grep -q Success; then
  desired=down reason="offline"
else
  desired=up reason="online, inside ${START_HOUR}:00-${STOP_HOUR}:00"
fi

if ! docker info >/dev/null 2>&1; then
  # Nothing runs without the engine, so "down" is already satisfied; only start the engine for "up".
  if [[ $desired == up ]]; then
    log "Docker engine not running, launching Rancher Desktop ($reason)"
    open -a "Rancher Desktop"
  fi
  exit 0
fi

running=$(compose ps -q --status running)
if [[ $desired == up && -z $running ]]; then
  log "starting stack ($reason)"
  compose up -d
elif [[ $desired == down && -n $running ]]; then
  log "stopping stack ($reason)"
  compose stop
fi
