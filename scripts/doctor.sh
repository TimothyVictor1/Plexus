#!/usr/bin/env bash
# What is running, what is not, and what to do about it.
set -uo pipefail

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FAILED=1; }
note() { printf '      %s\n' "$1"; }
FAILED=0

# Docker Desktop's control socket can wedge while its containers keep serving, and then every
# docker command hangs forever. Bound the check so this script always finishes and says so.
docker_ok() {
  ( docker info >/dev/null 2>&1 ) &
  local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt 10 ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null
    return 2
  fi
  wait "$pid"
}

echo "Docker"
docker_ok
case "$?" in
  2) bad "Docker is not answering (its containers may still be running)"
     note "fix: quit and reopen Docker Desktop, then 'make up'" ;;
esac
if docker_ok; then
  ok "daemon running"
  unhealthy=$(docker compose ps --format '{{.Service}} {{.Status}}' 2>/dev/null | grep -v 'Up' || true)
  if [ -z "$unhealthy" ]; then
    ok "$(docker compose ps --format '{{.Service}}' 2>/dev/null | wc -l | tr -d ' ') services up"
  else
    bad "some services are down:"; echo "$unhealthy" | sed 's/^/      /'
    note "fix: make up"
  fi
elif [ "$?" -ne 2 ]; then
  bad "Docker is not running"; note "fix: open Docker Desktop, then make up"
fi

echo "API (:8000)"
code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://localhost:8000/v1/health 2>/dev/null || echo 000)
if [ "$code" = "200" ]; then ok "healthy"; else bad "not responding (HTTP $code)"; note "fix: make up"; fi

echo "Database"
count=$(curl -s -m 20 http://localhost:8000/v1/org/status 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("process_count",0))' 2>/dev/null || echo 0)
if [ "$count" -gt 0 ] 2>/dev/null; then ok "$count ways of working found"; else bad "no data"; note "fix: make seed"; fi

echo "Console (:3000)"
code=$(curl -s -m 25 -o /dev/null -w '%{http_code}' http://localhost:3000/en 2>/dev/null || echo 000)
case "$code" in
  200) ok "serving" ;;
  000) bad "not running"; note "fix: make console" ;;
  500) bad "returning 500, usually a stale build cache"; note "fix: make console-reset" ;;
  *)   bad "unexpected HTTP $code"; note "fix: make console-reset" ;;
esac

echo
if [ "$FAILED" -eq 0 ]; then
  echo "Everything is running. Open http://localhost:3000/en"
else
  echo "Run the suggested fix above, then 'make doctor' again."
fi
exit $FAILED
