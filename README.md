# Foundry Bridge

**Python CLI tools for Palantir AIP Agents and Foundry Ontology — with MCP and Claude agentic loop**

Four Python scripts that provide command-line access to Palantir's AIP Agents API v2 and Foundry REST API v2, plus an MCP server that exposes all Foundry operations as tools, and a Claude-powered agentic loop that can autonomously execute multi-step Foundry tasks.

## What It Does

| Tool | Purpose | API |
|------|---------|-----|
| `foundry_agent.py` | Conversational AI via AIP Agents | AIP Agents API v2 |
| `foundry_bridge.py` | CRUD operations on Ontology Memory Objects | Foundry REST API v2 |
| `foundry_mcp_server.py` | MCP server — exposes Foundry tools over stdio | MCP (stdio transport) |
| `claude_agent.py` | Claude agentic loop over Foundry MCP tools | Anthropic SDK + MCP |

### foundry_agent.py — Talk to AIP Agents

- **Blocking mode**: Send a message, wait for complete response
- **Streaming mode**: Real-time token-by-token output (raw chunked markdown)
- **Interactive mode**: Multi-turn conversation in the terminal
- **Session management**: Create, resume, and list conversation sessions
- **Post-stream metadata**: Retrieves token counts via Content endpoint after streaming

### foundry_bridge.py — Read/Write Ontology Objects

- **List** all memory objects (sorted by timestamp, newest first)
- **Search** by content keyword
- **Create** new memory objects with sender attribution and UTC timestamps
- **Delete** by primary key
- **Status check** with full ontology summary (object types, action types, counts)

### foundry_mcp_server.py — MCP Server

Runs as an MCP server over stdio, exposing all Foundry Bridge operations as structured MCP tools:

| Tool | Description |
|------|-------------|
| `foundry_list_memories` | List all memory objects |
| `foundry_search_memories` | Search memories by keyword |
| `foundry_create_memory` | Create a new memory object |
| `foundry_delete_memory` | Delete a memory object by primary key |
| `foundry_status` | Connection and ontology status |

Compatible with any MCP client: Claude Desktop, `claude_agent.py`, or custom integrations.

### claude_agent.py — Claude Agentic Loop

Launches `foundry_mcp_server.py` as a subprocess, discovers its tools, and runs a Claude-powered agentic loop that can autonomously execute multi-step Foundry tasks. Claude decides which tools to call, processes the results, and iterates until the task is complete.

- **Single task**: Give Claude a natural-language task — it calls the tools and returns the result
- **Interactive mode**: Multi-turn conversation backed by Foundry tools
- **Configurable model**: Set `ANTHROPIC_MODEL` env var (default: `claude-opus-4-5`)

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│   Your CLI /    │     │  Palantir Foundry     │     │   AIP Agent with    │
│   AI Agent      │────>│  REST API v2          │────>│   Long-Term Memory  │
│                 │     │  AIP Agents API v2    │     │   (Ontology Objects)│
└─────────────────┘     └──────────────────────┘     └─────────────────────┘

┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  claude_agent   │     │ foundry_mcp_server   │     │  Palantir Foundry   │
│  (Anthropic SDK)│────>│ (MCP stdio server)   │────>│  REST API v2        │
│  agentic loop   │     │ 5 Foundry tools      │     │  Ontology Objects   │
└─────────────────┘     └──────────────────────┘     └─────────────────────┘
```

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

This installs `requests`, `mcp`, and `anthropic`.

### 2. Configure

Copy the example config and fill in your Foundry details:

```bash
cp config.example.json config.json
```

Edit `config.json`:
```json
{
    "token_file": "/path/to/your/foundry_token.txt",
    "host": "https://your-instance.palantirfoundry.com",
    "agent_rid": "ri.aip-agents..agent.your-agent-rid-here",
    "ontology_api": "your-ontology-api-name",
    "memory_type": "YourMemoryObjectType",
    "create_action": "your-create-action-name",
    "delete_action": "your-delete-action-name"
}
```

Or use environment variables:
```bash
export FOUNDRY_TOKEN="your-bearer-token"
export FOUNDRY_HOST="https://your-instance.palantirfoundry.com"
export FOUNDRY_AGENT_RID="ri.aip-agents..agent.xxx"

# For claude_agent.py:
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-opus-4-5"   # optional, this is the default
```

### 3. Test Connection

```bash
python foundry_agent.py --status
python foundry_bridge.py --status
python claude_agent.py --status
```

### 4. Use

```bash
# Talk to your AIP Agent (blocking)
python foundry_agent.py --talk "What do you remember about this project?"

# Stream response in real-time
python foundry_agent.py --stream "Summarize the current state of everything"

# Interactive multi-turn chat
python foundry_agent.py --interactive

# Create a memory object
python foundry_bridge.py --create "Important milestone: v1.0 deployed"

# Search memories
python foundry_bridge.py --search "milestone"

# List all memories
python foundry_bridge.py --list

# Run the MCP server standalone (for Claude Desktop or other MCP clients)
python foundry_mcp_server.py

# Claude agentic loop — single task
python claude_agent.py --task "List my 5 most recent memories and summarise them"
python claude_agent.py --task "Search for memories about 'deployment' and create a summary memory"

# Claude agentic loop — interactive
python claude_agent.py --interactive
```

## Streaming Implementation Notes

Palantir's AIP Agents streaming endpoint returns **raw chunked bytes of markdown**, not standard SSE (`text/event-stream`). Key implementation details:

```python
# CORRECT: Use iter_content with stream=True
with requests.post(url, headers=headers, json=body, stream=True) as resp:
    for chunk in resp.iter_content(chunk_size=None):
        if chunk:
            text = chunk.decode('utf-8')
            print(text, end='', flush=True)

# WRONG: Don't use sseclient or expect SSE format
```

- Token counts require a **separate** `GET .../content` call after the stream completes
- Each session supports one exchange in-flight at a time
- `messageId` (UUID) enables mid-stream cancellation via the cancel endpoint

## Windows Unicode Fix

Both scripts include a Windows cp1252 encoding fix. Foundry agents return markdown with Unicode characters (math symbols, special chars) that crash Windows console:

```python
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```

This is required for any Python script that prints Foundry API output on Windows. `foundry_mcp_server.py` wraps only `stderr` (stdout is reserved for MCP JSON-RPC transport).

## Configuration Priority

1. Environment variables (highest priority)
2. `config.json` file
3. Defaults (will error if required values missing)

| Environment Variable | Config Key | Used By |
|---------------------|------------|---------|
| `FOUNDRY_TOKEN` | - | All scripts (direct token) |
| `FOUNDRY_TOKEN_FILE` | `token_file` | All scripts (path to token file) |
| `FOUNDRY_HOST` | `host` | All scripts |
| `FOUNDRY_AGENT_RID` | `agent_rid` | foundry_agent.py |
| `FOUNDRY_ONTOLOGY_API` | `ontology_api` | foundry_bridge.py, foundry_mcp_server.py, claude_agent.py |
| `FOUNDRY_MEMORY_TYPE` | `memory_type` | foundry_bridge.py, foundry_mcp_server.py, claude_agent.py |
| `FOUNDRY_CREATE_ACTION` | `create_action` | foundry_bridge.py, foundry_mcp_server.py, claude_agent.py |
| `FOUNDRY_DELETE_ACTION` | `delete_action` | foundry_bridge.py, foundry_mcp_server.py, claude_agent.py |
| `ANTHROPIC_API_KEY` | - | claude_agent.py |
| `ANTHROPIC_MODEL` | - | claude_agent.py (default: `claude-opus-4-5`) |

## API Reference

### AIP Agents API v2 (foundry_agent.py)

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Create Session | POST | `/api/v2/aipAgents/agents/{agentRid}/sessions` |
| Blocking Continue | POST | `/api/v2/aipAgents/agents/{agentRid}/sessions/{sessionRid}/blockingContinue` |
| Streaming Continue | POST | `/api/v2/aipAgents/agents/{agentRid}/sessions/{sessionRid}/streamingContinue` |
| Get Content | GET | `/api/v2/aipAgents/agents/{agentRid}/sessions/{sessionRid}/content` |
| Cancel Exchange | POST | `/api/v2/aipAgents/agents/{agentRid}/sessions/{sessionRid}/cancel` |
| List Sessions | GET | `/api/v2/aipAgents/agents/{agentRid}/sessions` |

### Foundry REST API v2 (foundry_bridge.py)

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List Objects | GET | `/api/v2/ontologies/{ontologyApi}/objects/{objectType}` |
| Search Objects | POST | `/api/v2/ontologies/{ontologyApi}/objects/{objectType}/search` |
| Apply Action | POST | `/api/v2/ontologies/{ontologyApi}/actions/{actionType}/apply` |
| Get Ontology | GET | `/api/v2/ontologies/{ontologyApi}` |
| List Object Types | GET | `/api/v2/ontologies/{ontologyApi}/objectTypes` |
| List Action Types | GET | `/api/v2/ontologies/{ontologyApi}/actionTypes` |

## Use Cases

- **AI Agent Memory**: Give your AI agents persistent memory across sessions via Foundry Ontology
- **CLI Querying**: Query AIP Agents from terminal workflows, CI/CD pipelines, or automation scripts
- **Knowledge Management**: Build organizational memory systems backed by Palantir's enterprise platform
- **Multi-Agent Systems**: Bridge multiple AI agents through a shared Foundry Ontology as persistent memory layer
- **MCP Integration**: Connect Claude Desktop or any MCP-compatible client directly to Foundry
- **Agentic Automation**: Let Claude autonomously perform multi-step memory management tasks

## Requirements

- Python 3.10+
- `requests>=2.28.0`
- `mcp>=1.29.1` (for `foundry_mcp_server.py` and `claude_agent.py`)
- `anthropic>=1.7.0` (for `claude_agent.py`)
- Palantir Foundry instance with AIP Agents enabled
- Valid Foundry bearer token with appropriate permissions
- Anthropic API key (for `claude_agent.py` only)

### Claude Desktop Integration

To use `foundry_mcp_server.py` with Claude Desktop, add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "foundry-bridge": {
      "command": "python",
      "args": ["/absolute/path/to/foundry_mcp_server.py"],
      "env": {
        "FOUNDRY_TOKEN": "your-bearer-token",
        "FOUNDRY_HOST": "https://your-instance.palantirfoundry.com",
        "FOUNDRY_ONTOLOGY_API": "your-ontology-api-name",
        "FOUNDRY_MEMORY_TYPE": "YourMemoryObjectType",
        "FOUNDRY_CREATE_ACTION": "your-create-action-name",
        "FOUNDRY_DELETE_ACTION": "your-delete-action-name"
      }
    }
  }
}
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the [MIT License](LICENSE).

Unless you explicitly state otherwise, any contribution intentionally submitted for inclusion in Foundry Bridge by you shall be licensed as MIT, without any additional terms or conditions.
