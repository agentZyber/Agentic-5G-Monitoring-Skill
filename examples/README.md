# Examples

Copy-paste walkthroughs against a running toolkit app (`make run-toolkit`, default
`http://localhost:5001`). Each script is plain `curl` — no client libraries needed.

| Script | What it shows |
|---|---|
| [`talk_to_network.sh`](talk_to_network.sh) | health → tools → ask the agent → event ingest/query → AG-UI stream |
| [`intent_approval_flow.sh`](intent_approval_flow.sh) | the full draft → dry-run → submit → **human approve** → apply lifecycle |
| [`agent_protocols.sh`](agent_protocols.sh) | the same toolkit over **A2A** (card + JSON-RPC task), **ACP**, **MCP**, OASF/DID descriptors |

MCP from an agent client instead: `make mcp-stdio` and point Claude Code/Desktop (or any MCP
client) at it — the same tools appear there.
