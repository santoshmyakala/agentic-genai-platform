#!/usr/bin/env bash
# Container smoke test without model credentials: health, input validation and metrics must work.
set -euo pipefail
: "${IMAGE:?IMAGE must be set}"
docker run -d --name copilot-smoke -p 8080:8080 "$IMAGE" >/dev/null
trap 'docker rm -f copilot-smoke >/dev/null' EXIT
for _ in $(seq 1 30); do curl -fsS localhost:8080/healthz >/dev/null 2>&1 && break; sleep 1; done
curl -fsS localhost:8080/healthz
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8080/ask -H 'content-type: application/json' -d '{"question":""}')
[ "$code" = 422 ] || { echo "expected 422 for empty question, got $code"; exit 1; }
curl -fsS localhost:8080/metrics/ | grep -q opscopilot_answer_seconds
docker exec copilot-smoke id -u | grep -qx 10001 && echo "smoke OK (non-root)"
