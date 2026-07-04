#!/usr/bin/env bash
# The intent lifecycle: agent drafts/submits — a HUMAN approves — only then does apply work.
# Uses the A2A skill face for the agent-side steps so no LLM is needed for this walkthrough.
set -euo pipefail
BASE="${CORELAB_URL:-http://localhost:5001}"

echo "== 1) draft (agent-side) =="
DRAFT=$(curl -s -X POST "$BASE/a2a/skills/draft_intent" -H 'Content-Type: application/json' -d '{
  "name": "Keep URLLC slice latency under 15ms",
  "object_type": "NETWORK_SLICE", "object_instance": "slice-urllc-01",
  "metric": "latency_ms", "condition": "IS_LESS_THAN", "value": 15
}')
echo "$DRAFT" | python3 -m json.tool | head -25
ID=$(echo "$DRAFT" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['intent_id'])")
echo "intent_id=$ID"

echo "== 2) dry-run (what WOULD happen) =="
curl -s -X POST "$BASE/a2a/skills/dry_run_intent" -H 'Content-Type: application/json' \
  -d "{\"intent_id\": \"$ID\"}" | python3 -m json.tool

echo "== 3) submit for approval =="
curl -s -X POST "$BASE/a2a/skills/submit_intent_for_approval" -H 'Content-Type: application/json' \
  -d "{\"intent_id\": \"$ID\"}" | python3 -m json.tool

echo "== 4) try to apply WITHOUT approval (must be blocked) =="
curl -s -X POST "$BASE/a2a/skills/apply_intent" -H 'Content-Type: application/json' \
  -d "{\"intent_id\": \"$ID\"}" | python3 -m json.tool

echo "== 5) the HUMAN approves (REST-only — not an agent tool) =="
curl -s -X POST "$BASE/intents/$ID/approve" -H 'Content-Type: application/json' \
  -d '{"approver": "you@example.org"}' | python3 -m json.tool | head -12

echo "== 6) apply (now allowed; simulated executor by default) =="
curl -s -X POST "$BASE/a2a/skills/apply_intent" -H 'Content-Type: application/json' \
  -d "{\"intent_id\": \"$ID\"}" | python3 -m json.tool

echo "== 7) audit trail =="
curl -s "$BASE/intents/$ID" | python3 -c "import json,sys; [print(h) for h in json.load(sys.stdin)['history']]"
