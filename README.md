# Foundry Bridge

**Python CLI tools for Palantir AIP Agents and Foundry Ontology**

Two lightweight Python scripts that provide command-line access to Palantir's AIP Agents API v2 and Foundry REST API v2. Built for AI agent systems that need persistent memory through Palantir Foundry.

## What It Does

| Tool | Purpose | API |
|------|---------|-----|
| `foundry_agent.py` | Conversational AI via AIP Agents | AIP Agents API v2 |
| `foundry_bridge.py` | CRUD operations on Ontology Memory Objects | Foundry REST API v2 |

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

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│   Your CLI /    │     │  Palantir Foundry     │     │   AIP Agent with    │
│   AI Agent      │────>│  REST API v2          │────>│   Long-Term Memory  │
│                 │     │  AIP Agents API v2    │     │   (Ontology Objects)│
└─────────────────┘     └──────────────────────┘     └─────────────────────┘
```

## Quick Start

### 1. Install

```bash
pip install requests
```

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
```

### 3. Test Connection

```bash
python foundry_agent.py --status
python foundry_bridge.py --status
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

This is required for any Python script that prints Foundry API output on Windows.

## Configuration Priority

1. Environment variables (highest priority)
2. `config.json` file
3. Defaults (will error if required values missing)

| Environment Variable | Config Key | Used By |
|---------------------|------------|---------|
| `FOUNDRY_TOKEN` | - | Both (direct token) |
| `FOUNDRY_TOKEN_FILE` | `token_file` | Both (path to token file) |
| `FOUNDRY_HOST` | `host` | Both |
| `FOUNDRY_AGENT_RID` | `agent_rid` | foundry_agent.py |
| `FOUNDRY_ONTOLOGY_API` | `ontology_api` | foundry_bridge.py |
| `FOUNDRY_MEMORY_TYPE` | `memory_type` | foundry_bridge.py |
| `FOUNDRY_CREATE_ACTION` | `create_action` | foundry_bridge.py |
| `FOUNDRY_DELETE_ACTION` | `delete_action` | foundry_bridge.py |

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

## Requirements

- Python 3.8+
- `requests` library
- Palantir Foundry instance with AIP Agents enabled
- Valid Foundry bearer token with appropriate permissions

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the [MIT License](LICENSE).

Unless you explicitly state otherwise, any contribution intentionally submitted for inclusion in Foundry Bridge by you shall be licensed as MIT, without any additional terms or conditions.
