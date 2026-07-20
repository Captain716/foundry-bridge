"""
Foundry Bridge — CLI to Palantir Foundry Ontology (Memory Objects)

A Python CLI client for reading and writing Ontology Objects in Palantir Foundry
via the REST API v2. Designed for use with AIP Agents that have Long-Term Memory
backed by Ontology Objects.

ARCHITECTURE:
  CLI -> Foundry REST API v2 -> Ontology -> Memory Objects

OPERATIONS:
  - List all memory objects (sorted by timestamp, newest first)
  - Search memory objects by content keyword
  - Create new memory objects (with sender attribution)
  - Delete memory objects by primary key
  - Connection status check with ontology summary

PREREQUISITES:
  - Palantir Foundry token (stored in file or environment variable)
  - Network access to Foundry instance (check VPN split tunneling if applicable)
  - Ontology with Memory object type and create/delete actions configured

CONFIGURATION:
  Set via environment variables or config.json:
    FOUNDRY_TOKEN_FILE    - Path to file containing Foundry bearer token
    FOUNDRY_TOKEN         - Direct token (alternative to file)
    FOUNDRY_HOST          - Foundry instance URL
    FOUNDRY_ONTOLOGY_API  - Ontology API name
    FOUNDRY_MEMORY_TYPE   - Memory object type API name
    FOUNDRY_CREATE_ACTION - Create memory action API name
    FOUNDRY_DELETE_ACTION - Delete memory action API name

USAGE:
  python foundry_bridge.py --connect                    (quick connectivity check)
  python foundry_bridge.py --create "Memory content here"
  python foundry_bridge.py --create "Memory content" --sender "My Agent"
  python foundry_bridge.py --list
  python foundry_bridge.py --search "keyword"
  python foundry_bridge.py --delete <primaryKey>
  python foundry_bridge.py --status

LICENSE: MIT
"""

import os
import sys
import io
import json
import requests
from datetime import datetime, timezone

# === UNICODE FIX (Windows) ===
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# === CONFIGURATION ===
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

def load_config():
    """Load configuration from config.json or environment variables.

    Priority: Environment variables > config.json > defaults
    """
    config = {
        'token_file': '',
        'host': '',
        'ontology_api': '',
        'memory_type': '',
        'create_action': '',
        'delete_action': ''
    }

    # Load from config.json if it exists
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            file_config = json.load(f)
            config.update(file_config)

    # Override with environment variables
    env_map = {
        'FOUNDRY_TOKEN_FILE': 'token_file',
        'FOUNDRY_HOST': 'host',
        'FOUNDRY_ONTOLOGY_API': 'ontology_api',
        'FOUNDRY_MEMORY_TYPE': 'memory_type',
        'FOUNDRY_CREATE_ACTION': 'create_action',
        'FOUNDRY_DELETE_ACTION': 'delete_action'
    }
    for env_key, config_key in env_map.items():
        if os.environ.get(env_key):
            config[config_key] = os.environ[env_key]

    return config

CONFIG = load_config()

def get_api_base():
    """Build API base URL from config."""
    return f"{CONFIG['host']}/api/v2/ontologies/{CONFIG['ontology_api']}"

# === AUTH ===
def get_token():
    """Read Foundry token from secure storage."""
    # Try direct environment variable first
    if os.environ.get('FOUNDRY_TOKEN'):
        return os.environ['FOUNDRY_TOKEN']

    token_file = CONFIG.get('token_file', '')
    if not token_file or not os.path.exists(token_file):
        print("ERROR: Token not found.")
        print("Options:")
        print("  1. Set FOUNDRY_TOKEN environment variable")
        print("  2. Set FOUNDRY_TOKEN_FILE env var pointing to token file")
        print("  3. Add 'token_file' to config.json")
        print("  Generate tokens: Foundry > Account > Settings > Tokens")
        return None
    with open(token_file) as f:
        return f.read().strip()

def get_headers():
    """Get authorization headers for Foundry API."""
    token = get_token()
    if not token:
        return None
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

# === DTG ===
def get_dtg():
    """Get current timestamp in DTG format."""
    now = datetime.now()
    return now.strftime('%Y%b%d @%H%M%S.') + str(now.microsecond // 100000) + now.strftime(' %a').upper()

# === MEMORY OPERATIONS ===
def list_memories(max_results=50):
    """List all Memory Objects (sorted by timestamp, newest first)."""
    headers = get_headers()
    if not headers:
        return None

    url = f'{get_api_base()}/objects/{CONFIG["memory_type"]}'
    params = {'pageSize': max_results}

    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 200:
        data = resp.json()
        objects = data.get('data', [])
        # Sort by timestamp descending (newest first) in Python
        # NOTE: orderBy param may return HTTP 400 on some object types
        objects.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return objects
    else:
        print(f"ERROR: {resp.status_code}")
        print(resp.text[:500])
        return None

def search_memories(keyword):
    """Search Memory Objects by content keyword."""
    headers = get_headers()
    if not headers:
        return None

    url = f'{get_api_base()}/objects/{CONFIG["memory_type"]}/search'
    body = {
        'where': {
            'type': 'contains',
            'field': 'content',
            'value': keyword
        }
    }

    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code == 200:
        data = resp.json()
        return data.get('data', [])
    else:
        print(f"ERROR: {resp.status_code}")
        print(resp.text[:500])
        return None

def create_memory(content, sender='CLI Agent'):
    """Create a Memory Object via Ontology Action."""
    headers = get_headers()
    if not headers:
        return None

    url = f'{get_api_base()}/actions/{CONFIG["create_action"]}/apply'

    dtg = get_dtg()
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    body = {
        'parameters': {
            'content': content,
            'sender': sender,
            'timestamp': timestamp
        }
    }

    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code in (200, 201, 204):
        print(f"SUCCESS: Memory created")
        print(f"  DTG: {dtg}")
        print(f"  Sender: {sender}")
        print(f"  Content: {content[:200]}")
        print(f"  Timestamp: {timestamp}")
        return True
    else:
        print(f"ERROR: {resp.status_code}")
        error_text = resp.text[:1000]
        print(error_text)
        try:
            err = resp.json()
            if 'errorName' in err:
                print(f"  Error Name: {err['errorName']}")
            if 'errorInstanceId' in err:
                print(f"  Error ID: {err['errorInstanceId']}")
        except Exception:
            pass
        return False

def delete_memory(primary_key):
    """Delete a Memory Object by primary key."""
    headers = get_headers()
    if not headers:
        return None

    url = f'{get_api_base()}/actions/{CONFIG["delete_action"]}/apply'
    body = {
        'parameters': {
            'memory': primary_key
        }
    }

    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code in (200, 201, 204):
        print(f"SUCCESS: Memory deleted")
        print(f"  Primary Key: {primary_key}")
        return True
    else:
        print(f"ERROR: {resp.status_code}")
        print(resp.text[:500])
        return False

def connect():
    """Test connectivity to Foundry and verify credentials.

    Lightweight check — just authenticates and confirms the ontology is reachable.
    Use --status for a full summary of object types, actions, and memory counts.
    """
    headers = get_headers()
    if not headers:
        return False

    dtg = get_dtg()
    print("=" * 70)
    print(f"FOUNDRY BRIDGE -- CONNECT -- {dtg}")
    print("=" * 70)
    print(f"  Host:     {CONFIG['host']}")
    print(f"  Ontology: {CONFIG['ontology_api']}")

    resp = requests.get(
        f'{CONFIG["host"]}/api/v2/ontologies/{CONFIG["ontology_api"]}',
        headers=headers
    )
    if resp.status_code == 200:
        ont = resp.json()
        print(f"  Status:   CONNECTED")
        print(f"  Display:  {ont.get('displayName', 'N/A')}")
        print(f"  RID:      {ont.get('rid', 'N/A')}")
        print("=" * 70)
        print("CONNECTED")
        print("=" * 70)
        return True
    else:
        print(f"  Status:   FAILED ({resp.status_code})")
        if resp.status_code in (401, 403):
            print("  Check: Token may be expired or lack Ontology permissions")
        elif resp.status_code == 404:
            print("  Check: Host URL or ontology API name may be incorrect")
        else:
            print(f"  Response: {resp.text[:200]}")
        print("=" * 70)
        print("NOT CONNECTED")
        print("=" * 70)
        return False

def get_status():
    """Get connection status and ontology summary."""
    headers = get_headers()
    if not headers:
        return None

    dtg = get_dtg()
    print("=" * 70)
    print(f"FOUNDRY BRIDGE STATUS -- {dtg}")
    print("=" * 70)

    # Test connection
    resp = requests.get(f'{CONFIG["host"]}/api/v2/ontologies/{CONFIG["ontology_api"]}', headers=headers)
    if resp.status_code == 200:
        ont = resp.json()
        print(f"  Connection: ONLINE")
        print(f"  Ontology: {ont.get('displayName', 'N/A')}")
        print(f"  API Name: {ont.get('apiName', 'N/A')}")
        print(f"  RID: {ont.get('rid', 'N/A')}")
    else:
        print(f"  Connection: BLOCKED ({resp.status_code})")
        print(f"  Check: VPN split tunneling (python.exe may need to be excluded)")
        return False

    # Count memories
    memories = list_memories(200)
    if memories is not None:
        print(f"  Memory Objects: {len(memories)}")
        if memories:
            print(f"  Latest Memory: {memories[0].get('content', 'N/A')[:80]}")

    # Count object types
    resp2 = requests.get(f'{get_api_base()}/objectTypes', headers=headers)
    if resp2.status_code == 200:
        types = resp2.json().get('data', [])
        print(f"  Object Types: {len(types)}")
        for t in types:
            print(f"    - {t.get('displayName', 'N/A')} ({t.get('apiName', 'N/A')})")

    # Count actions
    resp3 = requests.get(f'{get_api_base()}/actionTypes', headers=headers)
    if resp3.status_code == 200:
        actions = resp3.json().get('data', [])
        print(f"  Action Types: {len(actions)}")
        for a in actions:
            print(f"    - {a.get('displayName', 'N/A')} ({a.get('apiName', 'N/A')})")

    print("=" * 70)
    print("BRIDGE STATUS: OPERATIONAL")
    print("=" * 70)
    return True

def format_memory(obj):
    """Format a Memory Object for display.
    NOTE: Foundry API v2 returns flat objects -- properties at top level.
    """
    ts = obj.get('timestamp', 'N/A')
    if ts and ts != 'N/A':
        ts = ts[:19].replace('T', ' ')
    lines = [
        f"  [{obj.get('primaryKey_', 'N/A')}]",
        f"    Sender: {obj.get('sender', 'N/A')}",
        f"    Content: {obj.get('content', 'N/A')[:200]}",
        f"    Timestamp: {ts}",
    ]
    return "\n".join(lines)

# === CLI ===
def main():
    dtg = get_dtg()
    print("=" * 70)
    print(f"FOUNDRY BRIDGE -- {dtg}")
    print("Palantir Foundry Ontology Client (REST API v2)")
    print("=" * 70)

    if len(sys.argv) < 2:
        print("\nUsage:")
        print('  python foundry_bridge.py --connect                    Quick connectivity check')
        print('  python foundry_bridge.py --status                     Full connection status')
        print('  python foundry_bridge.py --list                       List all memories')
        print('  python foundry_bridge.py --search "keyword"           Search memories')
        print('  python foundry_bridge.py --create "content"           Create memory')
        print('  python foundry_bridge.py --create "content" --sender "Name"  With sender')
        print('  python foundry_bridge.py --delete <primaryKey>        Delete memory')
        print("\nExamples:")
        print('  python foundry_bridge.py --connect')
        print('  python foundry_bridge.py --create "Important project milestone reached"')
        print('  python foundry_bridge.py --search "project"')
        print('  python foundry_bridge.py --status')
        return 1

    cmd = sys.argv[1]

    if cmd == '--connect':
        result = connect()
        return 0 if result else 1

    if cmd == '--status':
        get_status()
        return 0

    if cmd == '--list':
        memories = list_memories()
        if memories is not None:
            print(f"\nFound {len(memories)} memories:\n")
            if not memories:
                print("  (no memories stored yet)")
            for obj in memories:
                print(format_memory(obj))
                print()
        return 0

    if cmd == '--search':
        if len(sys.argv) < 3:
            print("ERROR: Search keyword required")
            return 1
        keyword = sys.argv[2]
        results = search_memories(keyword)
        if results is not None:
            print(f"\nFound {len(results)} memories matching '{keyword}':\n")
            for obj in results:
                print(format_memory(obj))
                print()
        return 0

    if cmd == '--create':
        content = None
        sender = 'CLI Agent'
        if '--content' in sys.argv:
            idx = sys.argv.index('--content')
            if idx + 1 < len(sys.argv):
                content = sys.argv[idx + 1]
        elif len(sys.argv) >= 3 and not sys.argv[2].startswith('--'):
            content = sys.argv[2]
        if not content:
            print("ERROR: Content required. Use: --create \"content\"")
            return 1
        if '--sender' in sys.argv:
            idx = sys.argv.index('--sender')
            if idx + 1 < len(sys.argv):
                sender = sys.argv[idx + 1]
        create_memory(content, sender)
        return 0

    if cmd == '--delete':
        if len(sys.argv) < 3:
            print("ERROR: Primary key required")
            return 1
        delete_memory(sys.argv[2])
        return 0

    print(f"Unknown command: {cmd}")
    return 1

if __name__ == '__main__':
    exit(main())
