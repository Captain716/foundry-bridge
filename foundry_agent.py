"""
Foundry Agent — CLI to Palantir AIP Agent (Conversational AI)

A Python CLI client for interacting with Palantir AIP Agents via the
AIP Agents API v2. Supports blocking, streaming, and interactive
multi-turn conversations.

ARCHITECTURE:
  CLI -> AIP Agents API v2 -> AIP Agent -> Knowledge Sources / Ontology

API WORKFLOW (Palantir AIP Agents API v2):
  1. Create Session           (POST .../agents/{agentRid}/sessions)
  2. Send Message (blocking)  (POST .../sessions/{sessionRid}/blockingContinue)
  3. Send Message (streaming) (POST .../sessions/{sessionRid}/streamingContinue)
  4. Get Content (post-stream) (GET .../sessions/{sessionRid}/content)
  5. Cancel Exchange           (POST .../sessions/{sessionRid}/cancel)
  6. List Sessions             (GET .../agents/{agentRid}/sessions)
  7. Get Session               (GET .../sessions/{sessionRid})

STREAMING NOTES:
  - Response is raw chunked bytes of markdown (NOT standard SSE text/event-stream)
  - Parse with requests.post(stream=True) + iter_content(), NOT sseclient
  - Token count and parameter updates require separate Content.get() call after stream
  - messageId (UUID) enables mid-stream cancellation via cancel endpoint
  - One exchange in-flight per session at a time

PREREQUISITES:
  - Palantir Foundry token (stored in file or environment variable)
  - Network access to Foundry instance (check VPN split tunneling if applicable)
  - Agent RID from your Foundry AIP Agent configuration

CONFIGURATION:
  Set via environment variables or config.json:
    FOUNDRY_TOKEN_FILE  - Path to file containing Foundry bearer token
    FOUNDRY_HOST        - Foundry instance URL (e.g., https://myorg.palantirfoundry.com)
    FOUNDRY_AGENT_RID   - Agent RID (ri.aip-agents..agent.xxx)

USAGE:
  python foundry_agent.py --talk "message"                          (blocking)
  python foundry_agent.py --stream "message"                        (streaming, real-time)
  python foundry_agent.py --talk "message" --session <sessionRid>   (continue session)
  python foundry_agent.py --stream "message" --session <sessionRid> (stream, continue)
  python foundry_agent.py --sessions                                (list sessions)
  python foundry_agent.py --status                                  (connection check)
  python foundry_agent.py --interactive                             (multi-turn chat)

LICENSE: MIT
"""

import os
import sys
import io
import json
import uuid
import requests
from datetime import datetime, timezone

# === UNICODE FIX (Windows) ===
# Windows console defaults to cp1252 which can't encode Unicode characters
# returned by AIP Agents (math symbols, emoji, special chars).
# This wraps stdout/stderr to handle any Unicode character gracefully.
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
        'agent_rid': ''
    }

    # Load from config.json if it exists
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            file_config = json.load(f)
            config.update(file_config)

    # Override with environment variables
    if os.environ.get('FOUNDRY_TOKEN_FILE'):
        config['token_file'] = os.environ['FOUNDRY_TOKEN_FILE']
    if os.environ.get('FOUNDRY_HOST'):
        config['host'] = os.environ['FOUNDRY_HOST']
    if os.environ.get('FOUNDRY_AGENT_RID'):
        config['agent_rid'] = os.environ['FOUNDRY_AGENT_RID']

    return config

CONFIG = load_config()

def get_api_base():
    """Build API base URL from config."""
    return f"{CONFIG['host']}/api/v2/aipAgents/agents/{CONFIG['agent_rid']}"

# === AUTH ===
def get_token():
    """Read Foundry token from secure storage."""
    token_file = CONFIG.get('token_file', '')

    # Try environment variable for direct token
    if os.environ.get('FOUNDRY_TOKEN'):
        return os.environ['FOUNDRY_TOKEN']

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
    """Get authorization headers for AIP Agents API."""
    token = get_token()
    if not token:
        return None
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

# === DTG (Date-Time Group) ===
def get_dtg():
    """Get current timestamp in DTG format (YYYYMMMdd @HHMMss.f DAY)."""
    now = datetime.now()
    return now.strftime('%Y%b%d @%H%M%S.') + str(now.microsecond // 100000) + now.strftime(' %a').upper()

# === SESSION OPERATIONS ===
def create_session():
    """Create a new conversation session with the Agent."""
    headers = get_headers()
    if not headers:
        return None

    url = f'{get_api_base()}/sessions'
    params = {'preview': 'true'}
    body = {}  # Empty body = use latest published agent version

    resp = requests.post(url, headers=headers, json=body, params=params)
    if resp.status_code in (200, 201):
        session = resp.json()
        session_rid = session.get('rid', 'N/A')
        print(f"  Session created: {session_rid[:60]}...")
        return session
    else:
        print(f"ERROR creating session: {resp.status_code}")
        print(resp.text[:500])
        return None

def send_message(session_rid, message):
    """Send a message and get response (blocking mode)."""
    headers = get_headers()
    if not headers:
        return None

    url = f'{get_api_base()}/sessions/{session_rid}/blockingContinue'
    params = {'preview': 'true'}

    trace_id = str(uuid.uuid4())
    body = {
        'userInput': {
            'text': message
        },
        'sessionTraceId': trace_id
    }

    resp = requests.post(url, headers=headers, json=body, params=params)
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"ERROR sending message: {resp.status_code}")
        print(resp.text[:500])
        return None

def send_message_streaming(session_rid, message):
    """Send a message and stream response in real time.

    The stream is raw chunked bytes of markdown -- NOT standard SSE.
    Token count requires a separate Content.get() call after stream completes.
    """
    headers = get_headers()
    if not headers:
        return None

    url = f'{get_api_base()}/sessions/{session_rid}/streamingContinue'
    params = {'preview': 'true'}

    trace_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    body = {
        'userInput': {
            'text': message
        },
        'sessionTraceId': trace_id,
        'messageId': message_id
    }

    full_response = ''
    try:
        with requests.post(url, headers=headers, json=body, params=params, stream=True) as resp:
            if resp.status_code != 200:
                print(f"ERROR streaming message: {resp.status_code}")
                print(resp.text[:500])
                return None
            for chunk in resp.iter_content(chunk_size=None):
                if chunk:
                    text = chunk.decode('utf-8')
                    full_response += text
                    print(text, end='', flush=True)
        print()  # Newline after stream completes
    except KeyboardInterrupt:
        print("\n  [Stream interrupted by user]")

    # Retrieve token count via Content endpoint
    tokens = 'N/A'
    try:
        content_url = f'{get_api_base()}/sessions/{session_rid}/content'
        content_resp = requests.get(content_url, headers=get_headers(), params={'preview': 'true'})
        if content_resp.status_code == 200:
            content = content_resp.json()
            exchanges = content.get('exchanges', [])
            if exchanges:
                last = exchanges[-1]
                result = last.get('result', {})
                tokens = result.get('totalTokensUsed', 'N/A')
    except Exception:
        pass  # Non-critical -- stream succeeded, metadata is bonus

    return {
        'response': full_response,
        'session_rid': session_rid,
        'tokens': tokens,
        'trace_id': trace_id,
        'message_id': message_id
    }

def list_sessions():
    """List all conversation sessions."""
    headers = get_headers()
    if not headers:
        return None

    url = f'{get_api_base()}/sessions'
    params = {'preview': 'true'}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 200:
        data = resp.json()
        return data.get('data', [])
    else:
        print(f"ERROR listing sessions: {resp.status_code}")
        print(resp.text[:500])
        return None

def get_status():
    """Check connection to AIP Agent."""
    headers = get_headers()
    if not headers:
        return False

    dtg = get_dtg()
    print("=" * 70)
    print(f"FOUNDRY AGENT STATUS -- {dtg}")
    print("=" * 70)
    print(f"  Agent RID: {CONFIG['agent_rid']}")
    print(f"  Host: {CONFIG['host']}")

    url = f'{get_api_base()}/sessions'
    params = {'preview': 'true'}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 200:
        sessions = resp.json().get('data', [])
        print(f"  Connection: ONLINE")
        print(f"  Sessions: {len(sessions)} found")
        if sessions:
            latest = sessions[0]
            meta = latest.get('metadata', {})
            print(f"  Latest Session: {meta.get('title', 'N/A')[:60]}")
            print(f"  Last Updated: {meta.get('updatedTime', 'N/A')[:19]}")
            print(f"  Messages: {meta.get('messageCount', 'N/A')}")
        print("=" * 70)
        print("AGENT STATUS: OPERATIONAL")
        print("=" * 70)
        return True
    else:
        print(f"  Connection: ERROR ({resp.status_code})")
        error_text = resp.text[:300]
        print(f"  Response: {error_text}")
        if resp.status_code == 403:
            print("  Check: VPN split tunneling (python.exe may need to be excluded)")
        elif resp.status_code == 401:
            print("  Check: Token may be expired or lack AIP Agent permissions")
        elif resp.status_code == 404:
            print("  Check: Agent RID may be incorrect, or AIP Agents API not enabled")
        print("=" * 70)
        print("AGENT STATUS: OFFLINE")
        print("=" * 70)
        return False

# === TALK (Single Message) ===
def talk(message, session_rid=None):
    """Send a single message to the Agent. Creates session if needed."""
    dtg = get_dtg()

    if session_rid:
        print(f"  Resuming session: {session_rid[:50]}...")
    else:
        print("  Creating new session...")
        session = create_session()
        if not session:
            return None
        session_rid = session['rid']

    print(f"  Sending message...")
    print(f"  You: {message[:200]}")
    print()

    result = send_message(session_rid, message)
    if result:
        response = result.get('agentMarkdownResponse', '(no response)')
        tokens = result.get('totalTokensUsed', 'N/A')
        interrupted = result.get('interruptedOutput', False)

        print("  " + "-" * 66)
        print(f"  AGENT RESPONSE:")
        print("  " + "-" * 66)
        print()
        for line in response.split('\n'):
            print(f"  {line}")
        print()
        print("  " + "-" * 66)
        print(f"  Tokens used: {tokens}")
        print(f"  Session: {session_rid[:60]}...")
        if interrupted:
            print("  WARNING: Response was interrupted/truncated")
        print(f"  DTG: {dtg}")

        return {
            'response': response,
            'session_rid': session_rid,
            'tokens': tokens,
            'trace_id': result.get('sessionTraceId', 'N/A')
        }
    return None

# === STREAM (Single Message, Real-Time) ===
def stream(message, session_rid=None):
    """Stream a single message from the Agent in real time. Creates session if needed."""
    dtg = get_dtg()

    if session_rid:
        print(f"  Resuming session: {session_rid[:50]}...")
    else:
        print("  Creating new session...")
        session = create_session()
        if not session:
            return None
        session_rid = session['rid']

    print(f"  Streaming response...")
    print(f"  You: {message[:200]}")
    print()
    print("  " + "-" * 66)
    print(f"  AGENT RESPONSE (streaming):")
    print("  " + "-" * 66)
    print()

    result = send_message_streaming(session_rid, message)
    if result:
        print()
        print("  " + "-" * 66)
        print(f"  Tokens used: {result['tokens']}")
        print(f"  Session: {session_rid[:60]}...")
        print(f"  DTG: {dtg}")

        return result
    return None

# === INTERACTIVE MODE ===
def interactive():
    """Multi-turn conversation with the Agent."""
    dtg = get_dtg()
    print()
    print("=" * 70)
    print(f"FOUNDRY AGENT -- INTERACTIVE MODE -- {dtg}")
    print("Type 'quit' or 'exit' to end. Type 'new' for new session.")
    print("=" * 70)
    print()

    print("  Connecting...")
    session = create_session()
    if not session:
        print("  FAILED to create session. Check status with --status")
        return

    session_rid = session['rid']
    print(f"  Connected. Session active.")
    print()

    while True:
        try:
            user_input = input("  YOU > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Session ended.")
            break

        if not user_input:
            continue
        if user_input.lower() in ('quit', 'exit', 'q'):
            print("  Session ended.")
            break
        if user_input.lower() == 'new':
            print("  Creating new session...")
            session = create_session()
            if session:
                session_rid = session['rid']
                print("  New session active.")
            continue

        result = send_message(session_rid, user_input)
        if result:
            response = result.get('agentMarkdownResponse', '(no response)')
            tokens = result.get('totalTokensUsed', 'N/A')
            print()
            print(f"  AGENT > {response}")
            print()
            print(f"  [{tokens} tokens]")
            print()
        else:
            print("  ERROR: No response from agent.")
            print()

# === CLI ===
def main():
    dtg = get_dtg()
    print("=" * 70)
    print(f"FOUNDRY AGENT -- {dtg}")
    print(f"AIP Agents API v2 Client")
    print(f"Agent: {CONFIG.get('agent_rid', 'NOT CONFIGURED')[:50]}...")
    print("=" * 70)

    if len(sys.argv) < 2:
        print("\nUsage:")
        print('  python foundry_agent.py --status                           Connection check')
        print('  python foundry_agent.py --sessions                         List sessions')
        print('  python foundry_agent.py --talk "message"                   Send message (blocking)')
        print('  python foundry_agent.py --stream "message"                 Send message (streaming)')
        print('  python foundry_agent.py --talk "message" --session <rid>   Continue session')
        print('  python foundry_agent.py --stream "message" --session <rid> Stream, continue session')
        print('  python foundry_agent.py --interactive                      Multi-turn chat')
        print("\nExamples:")
        print('  python foundry_agent.py --talk "What do you remember about this project?"')
        print('  python foundry_agent.py --stream "Summarize the current enterprise state"')
        print('  python foundry_agent.py --interactive')
        return 1

    cmd = sys.argv[1]

    if cmd == '--status':
        get_status()
        return 0

    if cmd == '--sessions':
        sessions = list_sessions()
        if sessions is not None:
            print(f"\nFound {len(sessions)} sessions:\n")
            if not sessions:
                print("  (no sessions yet)")
            for s in sessions:
                meta = s.get('metadata', {})
                rid = s.get('rid', 'N/A')
                title = meta.get('title', 'N/A')
                msgs = meta.get('messageCount', 0)
                updated = meta.get('updatedTime', 'N/A')[:19]
                print(f"  [{rid[:40]}...]")
                print(f"    Title: {title[:60]}")
                print(f"    Messages: {msgs}")
                print(f"    Updated: {updated}")
                print()
        return 0

    if cmd == '--talk':
        if len(sys.argv) < 3:
            print("ERROR: Message required")
            return 1
        message = sys.argv[2]
        session_rid = None
        if '--session' in sys.argv:
            idx = sys.argv.index('--session')
            if idx + 1 < len(sys.argv):
                session_rid = sys.argv[idx + 1]
        talk(message, session_rid)
        return 0

    if cmd == '--stream':
        if len(sys.argv) < 3:
            print("ERROR: Message required")
            return 1
        message = sys.argv[2]
        session_rid = None
        if '--session' in sys.argv:
            idx = sys.argv.index('--session')
            if idx + 1 < len(sys.argv):
                session_rid = sys.argv[idx + 1]
        stream(message, session_rid)
        return 0

    if cmd == '--interactive':
        interactive()
        return 0

    print(f"Unknown command: {cmd}")
    return 1

if __name__ == '__main__':
    exit(main())
