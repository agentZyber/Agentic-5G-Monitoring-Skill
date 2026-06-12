#!/usr/bin/env bash
# One toolkit, every agent-protocol face: A2A, ACP, MCP, OASF, ANP.
set -euo pipefail
BASE="${ZORTENET_URL:-http://localhost:5001}"

echo "== A2A: Agent Card =="
curl -s "$BASE/.well-known/agent-card.json" | python3 -c "
import json,sys; c=json.load(sys.stdin)
print(c['name'], '| skills:', len(c['skills']))"

echo "== A2A: full task over JSON-RPC (message/send) =="
curl -s -X POST "$BASE/a2a" -H 'Content-Type: application/json' -d '{
  "jsonrpc": "2.0", "id": 1, "method": "message/send",
  "params": {"message": {"kind": "message", "role": "user", "messageId": "m1",
             "parts": [{"kind": "text", "text": "How many tools do you have?"}]}}
}' | python3 -m json.tool | head -20

echo "== ACP: discover + run =="
curl -s "$BASE/acp/agents" | python3 -m json.tool
curl -s -X POST "$BASE/acp/runs" -H 'Content-Type: application/json' -d '{
  "agent_name": "zortenet-5g",
  "input": [{"parts": [{"content": "network status?", "content_type": "text/plain"}]}]
}' | python3 -m json.tool | head -15

echo "== MCP over Streamable HTTP: list tools =="
curl -s -X POST "$BASE/mcp" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}' | python3 -c "
import json,sys; tools=json.load(sys.stdin)['result']['tools']
print(len(tools), 'tools over MCP:', ', '.join(t['name'] for t in tools[:5]), '…')"

echo "== AGNTCY/OASF + ANP (experimental) descriptors =="
curl -s "$BASE/.well-known/oasf.json" | python3 -c "
import json,sys; r=json.load(sys.stdin)
print('OASF:', r['name'], '| locators:', [l['type'] for l in r['locators']])"
curl -s "$BASE/.well-known/did.json" | python3 -c "
import json,sys; d=json.load(sys.stdin); print('ANP DID:', d['id'], '(experimental, unsigned)')"
