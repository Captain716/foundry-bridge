# Foundry Bridge — Claude Code Context

This file is read automatically by [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
and by VS Code Server with the Claude extension. It provides project context for AI-assisted
development in this repo.

## Project Overview

Python CLI toolkit for Palantir Foundry Ontology and AIP Agents, with an MCP server and Claude
agentic loop built in.

| File | Purpose |
|------|---------|
| `foundry_bridge.py` | CRUD operations on Foundry Ontology memory objects (REST API v2) |
| `foundry_agent.py` | Conversational AIP Agent client (blocking + streaming) |
| `foundry_mcp_server.py` | MCP stdio server — exposes Foundry tools to any MCP client |
| `claude_agent.py` | Claude agentic loop via Anthropic SDK over the MCP server |
| `config.example.json` | Template config — copy to `config.json` and fill in your values |
| `requirements.txt` | Python dependencies |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Foundry credentials

```bash
cp config.example.json config.json
# Edit config.json with your Foundry host, token file path, ontology details
```

Or use environment variables (preferred for VS Code Server):

```bash
export FOUNDRY_TOKEN="your-bearer-token"
export FOUNDRY_HOST="https://your-instance.palantirfoundry.com"
export FOUNDRY_ONTOLOGY_API="your-ontology-api-name"
export FOUNDRY_MEMORY_TYPE="YourMemoryObjectType"
export FOUNDRY_CREATE_ACTION="your-create-action-name"
export FOUNDRY_DELETE_ACTION="your-delete-action-name"
```

### 3. Configure Anthropic credentials (for claude_agent.py)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-opus-4-0"   # optional, this is the default
```

## Running the scripts

```bash
# Check Foundry connectivity
python foundry_bridge.py --status
python foundry_agent.py --status

# Foundry memory CRUD
python foundry_bridge.py --list
python foundry_bridge.py --create "memory content here"
python foundry_bridge.py --search "keyword"
python foundry_bridge.py --delete <primaryKey>

# AIP Agent chat
python foundry_agent.py --talk "your message"
python foundry_agent.py --stream "your message"
python foundry_agent.py --interactive

# MCP server (stdio — used by MCP clients including claude_agent.py)
python foundry_mcp_server.py

# Claude agentic loop over Foundry tools
python claude_agent.py --status
python claude_agent.py --task "List my 5 most recent memories and summarise them"
python claude_agent.py --interactive
```

## Architecture

```
claude_agent.py  ──[stdio MCP]──>  foundry_mcp_server.py  ──[HTTP]──>  Palantir Foundry API
foundry_bridge.py                ──[HTTP]──>  Foundry REST API v2
foundry_agent.py                 ──[HTTP]──>  AIP Agents API v2
```

## Configuration priority

1. Environment variables (highest — recommended for VS Code Server)
2. `config.json` file
3. Defaults (errors if required values are missing)

## Key conventions

- All scripts use `requests` for HTTP (sync)
- `claude_agent.py` uses `asyncio` + `anthropic.AsyncAnthropic` + MCP client
- Token is always `****** in the `Authorization` header
- DTG (Date-Time Group) format: `YYYYMMMdd @HHMMss.f DAY` (e.g. `2026Sep23 @025700.3 TUE`)
- Memory objects: flat Foundry API v2 objects with `primaryKey_`, `sender`, `content`, `timestamp`

## Common tasks for Claude Code

- Add retry/backoff logic to Foundry HTTP calls
- Add pagination support to `foundry_list_memories`
- Write pytest tests for foundry_bridge.py and foundry_mcp_server.py
- Add streaming support to claude_agent.py
- Add a new MCP tool to foundry_mcp_server.py (follow the `@mcp.tool()` decorator pattern)
