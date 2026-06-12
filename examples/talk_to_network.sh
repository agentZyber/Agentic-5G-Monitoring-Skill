#!/usr/bin/env bash
# Talk to your (simulated) 5G network — REST face walkthrough.
set -euo pipefail
BASE="${ZORTENET_URL:-http://localhost:5001}"

echo "== health =="
curl -s "$BASE/health" | python3 -m json.tool

echo "== what tools does the agent have? =="
curl -s "$BASE/tools" | python3 -c "import json,sys; [print('-', t['name']) for t in json.load(sys.stdin)]"

echo "== seed a couple of events (replay would do this at scale) =="
curl -s -X POST "$BASE/events" -H 'Content-Type: application/json' -d '{
  "domain": "qos", "source": "demo", "entity_id": "ue-demo",
  "severity": "alert", "event_type": "QOS_MONITORING", "payload": {"latency_ms": 280}
}' > /dev/null
curl -s -X POST "$BASE/events" -H 'Content-Type: application/json' -d '{
  "externalId": "ue-demo", "type": "log", "locationInfo": {"cellId": "C7"}
}' > /dev/null
curl -s "$BASE/events/stats" | python3 -m json.tool

echo "== ask the agent (needs Ollama or another provider running) =="
curl -s -X POST "$BASE/agent/ask" -H 'Content-Type: application/json' \
  -d '{"message": "Anything wrong with ue-demo? Check recent events first."}' | python3 -m json.tool

echo "== same question over the AG-UI event stream =="
curl -sN -X POST "$BASE/agui/run" -H 'Content-Type: application/json' \
  -d '{"message": "Summarize network health."}' | head -20
