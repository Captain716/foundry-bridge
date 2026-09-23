"""
Foundry MCP Server — Exposes Foundry Bridge functions as MCP tools

Runs an MCP server over stdio so any MCP-compatible client (e.g. Claude Desktop,
claude_agent.py) can call Foundry Ontology operations as structured tool calls.

TOOLS EXPOSED:
  foundry_list_memories   — List all memory objects (newest first)
  foundry_search_memories — Search memory objects by keyword
  foundry_create_memory   — Create a new memory object
  foundry_delete_memory   — Delete a memory object by primary key
  foundry_status          — Return Foundry connection / ontology status

USAGE (stdio transport — used by MCP clients):
  python foundry_mcp_server.py

CONFIGURATION (same as foundry_bridge.py):
  Set via environment variables or config.json:
    FOUNDRY_TOKEN / FOUNDRY_TOKEN_FILE
    FOUNDRY_HOST
    FOUNDRY_ONTOLOGY_API
    FOUNDRY_MEMORY_TYPE
    FOUNDRY_CREATE_ACTION
    FOUNDRY_DELETE_ACTION

LICENSE: MIT
"""

import io
import json
import os
import sys
from datetime import datetime, timezone

import requests
from mcp.server.fastmcp import FastMCP

# === UNICODE FIX (Windows) ===
# Wrap stderr only — stdout is used by the MCP stdio transport for JSON-RPC
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# === CONFIGURATION (mirrors foundry_bridge.py) ===
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')


def _load_config() -> dict:
    config = {
        'token_file': '',
        'host': '',
        'ontology_api': '',
        'memory_type': '',
        'create_action': '',
        'delete_action': '',
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            config.update(json.load(f))
    env_map = {
        'FOUNDRY_TOKEN_FILE': 'token_file',
        'FOUNDRY_HOST': 'host',
        'FOUNDRY_ONTOLOGY_API': 'ontology_api',
        'FOUNDRY_MEMORY_TYPE': 'memory_type',
        'FOUNDRY_CREATE_ACTION': 'create_action',
        'FOUNDRY_DELETE_ACTION': 'delete_action',
    }
    for env_key, cfg_key in env_map.items():
        if os.environ.get(env_key):
            config[cfg_key] = os.environ[env_key]
    return config


CONFIG = _load_config()


def _api_base() -> str:
    return f"{CONFIG['host']}/api/v2/ontologies/{CONFIG['ontology_api']}"


def _get_token() -> str | None:
    if os.environ.get('FOUNDRY_TOKEN'):
        return os.environ['FOUNDRY_TOKEN']
    token_file = CONFIG.get('token_file', '')
    if token_file and os.path.exists(token_file):
        with open(token_file) as f:
            return f.read().strip()
    return None


def _headers() -> dict | None:
    token = _get_token()
    if not token:
        return None
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


# === CONSTANTS ===
STATUS_MAX_MEMORIES = 200  # Maximum memories fetched by foundry_status for the count display

# === MCP SERVER ===
mcp = FastMCP(
    name='foundry-bridge',
    instructions=(
        'Tools for reading and writing Palantir Foundry Ontology memory objects. '
        'Use foundry_status to verify connectivity before other operations.'
    ),
)


@mcp.tool()
def foundry_list_memories(max_results: int = 50) -> str:
    """List Foundry memory objects, sorted newest first.

    Args:
        max_results: Maximum number of memories to return (default 50).

    Returns:
        JSON string containing a list of memory objects, each with
        primaryKey_, sender, content, and timestamp fields.
    """
    headers = _headers()
    if not headers:
        return json.dumps({'error': 'Foundry token not configured'})

    url = f'{_api_base()}/objects/{CONFIG["memory_type"]}'
    resp = requests.get(url, headers=headers, params={'pageSize': max_results})
    if resp.status_code != 200:
        return json.dumps({'error': f'HTTP {resp.status_code}', 'detail': resp.text[:500]})

    objects = resp.json().get('data', [])
    objects.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return json.dumps({'count': len(objects), 'memories': objects})


@mcp.tool()
def foundry_search_memories(keyword: str) -> str:
    """Search Foundry memory objects by content keyword.

    Args:
        keyword: Substring to search for inside the content field.

    Returns:
        JSON string containing matching memory objects.
    """
    headers = _headers()
    if not headers:
        return json.dumps({'error': 'Foundry token not configured'})

    url = f'{_api_base()}/objects/{CONFIG["memory_type"]}/search'
    body = {
        'where': {
            'type': 'contains',
            'field': 'content',
            'value': keyword,
        }
    }
    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code != 200:
        return json.dumps({'error': f'HTTP {resp.status_code}', 'detail': resp.text[:500]})

    objects = resp.json().get('data', [])
    return json.dumps({'keyword': keyword, 'count': len(objects), 'memories': objects})


@mcp.tool()
def foundry_create_memory(content: str, sender: str = 'Claude Agent') -> str:
    """Create a new memory object in the Foundry Ontology.

    Args:
        content: The text content to store as a memory.
        sender:  Attribution label for who is creating the memory (default 'Claude Agent').

    Returns:
        JSON string confirming success or describing the error.
    """
    headers = _headers()
    if not headers:
        return json.dumps({'error': 'Foundry token not configured'})

    url = f'{_api_base()}/actions/{CONFIG["create_action"]}/apply'
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    body = {
        'parameters': {
            'content': content,
            'sender': sender,
            'timestamp': timestamp,
        }
    }
    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code in (200, 201, 204):
        return json.dumps({'success': True, 'sender': sender, 'timestamp': timestamp, 'content': content[:200]})

    return json.dumps({'error': f'HTTP {resp.status_code}', 'detail': resp.text[:500]})


@mcp.tool()
def foundry_delete_memory(primary_key: str) -> str:
    """Delete a memory object from the Foundry Ontology by its primary key.

    Args:
        primary_key: The primaryKey_ identifier of the memory object to delete.

    Returns:
        JSON string confirming deletion or describing the error.
    """
    headers = _headers()
    if not headers:
        return json.dumps({'error': 'Foundry token not configured'})

    url = f'{_api_base()}/actions/{CONFIG["delete_action"]}/apply'
    body = {'parameters': {'memory': primary_key}}
    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code in (200, 201, 204):
        return json.dumps({'success': True, 'deleted_key': primary_key})

    return json.dumps({'error': f'HTTP {resp.status_code}', 'detail': resp.text[:500]})


@mcp.tool()
def foundry_status() -> str:
    """Check connectivity to Palantir Foundry and return ontology summary.

    Returns:
        JSON string with connection status, ontology display name, memory
        object count, object types, and action types.
    """
    headers = _headers()
    if not headers:
        return json.dumps({'error': 'Foundry token not configured'})

    result: dict = {}

    # Ontology connection
    resp = requests.get(f'{CONFIG["host"]}/api/v2/ontologies/{CONFIG["ontology_api"]}', headers=headers)
    if resp.status_code != 200:
        return json.dumps({'status': 'OFFLINE', 'error': f'HTTP {resp.status_code}', 'detail': resp.text[:300]})

    ont = resp.json()
    result['status'] = 'ONLINE'
    result['ontology'] = ont.get('displayName', 'N/A')
    result['api_name'] = ont.get('apiName', 'N/A')
    result['rid'] = ont.get('rid', 'N/A')

    # Memory count
    mem_resp = requests.get(
        f'{_api_base()}/objects/{CONFIG["memory_type"]}',
        headers=headers,
        params={'pageSize': STATUS_MAX_MEMORIES},
    )
    if mem_resp.status_code == 200:
        memories = mem_resp.json().get('data', [])
        result['memory_count'] = len(memories)
        if memories:
            memories.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            result['latest_memory'] = memories[0].get('content', '')[:80]

    # Object types
    ot_resp = requests.get(f'{_api_base()}/objectTypes', headers=headers)
    if ot_resp.status_code == 200:
        result['object_types'] = [
            {'name': t.get('displayName', 'N/A'), 'api_name': t.get('apiName', 'N/A')}
            for t in ot_resp.json().get('data', [])
        ]

    # Action types
    at_resp = requests.get(f'{_api_base()}/actionTypes', headers=headers)
    if at_resp.status_code == 200:
        result['action_types'] = [
            {'name': a.get('displayName', 'N/A'), 'api_name': a.get('apiName', 'N/A')}
            for a in at_resp.json().get('data', [])
        ]

    return json.dumps(result)


if __name__ == '__main__':
    mcp.run(transport='stdio')
