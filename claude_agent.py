"""
Claude Agent — Agentic loop over Foundry MCP tools via Anthropic SDK

Launches foundry_mcp_server.py as a subprocess MCP server, connects to it
over stdio, discovers its tools, and runs a Claude-powered agentic loop that
can call Foundry Ontology operations until the task is complete.

ARCHITECTURE:
  claude_agent.py  ->  [stdio]  ->  foundry_mcp_server.py  ->  Palantir Foundry API

USAGE:
  python claude_agent.py --task "List all memories and summarise them"
  python claude_agent.py --task "Create a memory: project reached alpha"
  python claude_agent.py --interactive
  python claude_agent.py --status

CONFIGURATION:
  ANTHROPIC_API_KEY   — Anthropic API key (required)
  ANTHROPIC_MODEL     — Claude model to use (default: claude-opus-4-5)
  FOUNDRY_TOKEN / FOUNDRY_TOKEN_FILE / FOUNDRY_HOST / etc. — same as foundry_bridge.py

LICENSE: MIT
"""

import asyncio
import io
import json
import os
import sys
from datetime import datetime

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# === UNICODE FIX (Windows) ===
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# === CONFIGURATION ===
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-opus-4-0')
MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'foundry_mcp_server.py')
MAX_ITERATIONS = 20  # Safety cap on the agentic loop


# === DTG ===
def get_dtg() -> str:
    now = datetime.now()
    return now.strftime('%Y%b%d @%H%M%S.') + str(now.microsecond // 100000) + now.strftime(' %a').upper()


# === MCP TOOL HELPERS ===
def _mcp_tools_to_anthropic(mcp_tools: list) -> list[dict]:
    """Convert MCP tool definitions to Anthropic tool format."""
    anthropic_tools = []
    for tool in mcp_tools:
        # MCP tool.inputSchema is already JSON-Schema compatible
        schema = tool.inputSchema if tool.inputSchema else {'type': 'object', 'properties': {}}
        anthropic_tools.append({
            'name': tool.name,
            'description': tool.description or '',
            'input_schema': schema,
        })
    return anthropic_tools


# === AGENTIC LOOP ===
async def run_agent(task: str, verbose: bool = True) -> str:
    """Run the Claude agentic loop over Foundry MCP tools.

    Args:
        task:    Natural-language task for Claude to execute using the Foundry tools.
        verbose: Print step-by-step progress to stdout.

    Returns:
        Final text response from the agent.
    """
    if not ANTHROPIC_API_KEY:
        return 'ERROR: ANTHROPIC_API_KEY environment variable is not set.'

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[MCP_SERVER_SCRIPT],
        env=os.environ.copy(),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Discover tools from the MCP server
            tools_result = await session.list_tools()
            anthropic_tools = _mcp_tools_to_anthropic(tools_result.tools)

            if verbose:
                print(f'  Tools available: {[t["name"] for t in anthropic_tools]}')
                print()

            messages = [{'role': 'user', 'content': task}]
            system_prompt = (
                'You are a helpful assistant with access to Palantir Foundry tools. '
                'Use the available tools to complete the user\'s request. '
                'When you have finished and have enough information to give a complete answer, '
                'respond directly without calling any more tools.'
            )

            final_response = ''
            for iteration in range(MAX_ITERATIONS):
                if verbose:
                    print(f'  [Iteration {iteration + 1}] Calling Claude...')

                response = await client.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=anthropic_tools,
                    messages=messages,
                )

                # Collect text from this response; accumulate across iterations
                text_parts = [b.text for b in response.content if b.type == 'text']
                if text_parts:
                    final_response += ('\n' if final_response else '') + '\n'.join(text_parts)

                # End of agentic loop — Claude is done
                if response.stop_reason == 'end_turn':
                    if verbose:
                        print(f'  [Done — {iteration + 1} iteration(s)]')
                    break

                # Process tool calls
                tool_uses = [b for b in response.content if b.type == 'tool_use']
                if not tool_uses:
                    break

                # Add assistant turn to history
                messages.append({'role': 'assistant', 'content': response.content})

                # Execute each tool call via MCP and collect results
                tool_results = []
                for tool_use in tool_uses:
                    if verbose:
                        print(f'  [Tool call] {tool_use.name}({json.dumps(tool_use.input)[:120]})')

                    try:
                        result = await session.call_tool(tool_use.name, tool_use.input)
                        first = result.content[0] if result.content else None
                        content = first.text if (first and first.type == 'text') else ''
                    except Exception as exc:
                        content = json.dumps({'error': str(exc)})

                    if verbose:
                        print(f'  [Tool result] {content[:200]}')

                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': tool_use.id,
                        'content': content,
                    })

                # Add tool results to history
                messages.append({'role': 'user', 'content': tool_results})

            else:
                if verbose:
                    print(f'  [Warning] Reached max iterations ({MAX_ITERATIONS})')

            return final_response or 'Agent completed without producing a text response.'


# === ASYNC RUNNER ===
def run(task: str, verbose: bool = True) -> str:
    """Synchronous wrapper around the async agentic loop."""
    return asyncio.run(run_agent(task, verbose=verbose))


# === CLI ===
def main() -> int:
    dtg = get_dtg()
    print('=' * 70)
    print(f'CLAUDE AGENT -- {dtg}')
    print(f'Anthropic SDK + Foundry MCP Tools')
    print(f'Model: {MODEL}')
    print('=' * 70)

    if len(sys.argv) < 2:
        print('\nUsage:')
        print('  python claude_agent.py --task "your task here"    Run a single task')
        print('  python claude_agent.py --interactive              Multi-turn chat')
        print('  python claude_agent.py --status                   Check configuration')
        print('\nExamples:')
        print('  python claude_agent.py --task "List my most recent 5 memories"')
        print('  python claude_agent.py --task "Search memories for \'deployment\' and summarise them"')
        print('  python claude_agent.py --task "Store a memory: completed sprint 42"')
        return 1

    cmd = sys.argv[1]

    if cmd == '--status':
        print()
        print(f'  ANTHROPIC_API_KEY : {"SET" if ANTHROPIC_API_KEY else "NOT SET (required)"}')
        print(f'  Model             : {MODEL}')
        print(f'  MCP server script : {MCP_SERVER_SCRIPT}')
        print(f'  Script exists     : {os.path.exists(MCP_SERVER_SCRIPT)}')
        print()
        if not ANTHROPIC_API_KEY:
            print('  ERROR: Set ANTHROPIC_API_KEY to use this tool.')
            return 1
        print('  Running foundry_status via MCP...')
        result = run('Call the foundry_status tool and return its JSON output verbatim.', verbose=False)
        print()
        print(result)
        return 0

    if cmd == '--task':
        if len(sys.argv) < 3:
            print('ERROR: Task string required')
            return 1
        task = sys.argv[2]
        print(f'\n  Task: {task}')
        print()
        result = run(task)
        print()
        print('=' * 70)
        print('RESULT:')
        print('=' * 70)
        print(result)
        print('=' * 70)
        return 0

    if cmd == '--interactive':
        if not ANTHROPIC_API_KEY:
            print('ERROR: ANTHROPIC_API_KEY not set.')
            return 1
        print('\nInteractive mode. Type your task, then press Enter.')
        print("Type 'quit' or 'exit' to end.\n")
        while True:
            try:
                user_input = input('  YOU > ').strip()
            except (KeyboardInterrupt, EOFError):
                print('\n  Session ended.')
                break
            if not user_input:
                continue
            if user_input.lower() in ('quit', 'exit', 'q'):
                print('  Session ended.')
                break
            print()
            result = run(user_input)
            print()
            print(f'  CLAUDE > {result}')
            print()
        return 0

    print(f'Unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    exit(main())
