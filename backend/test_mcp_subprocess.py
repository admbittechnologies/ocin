"""Test Maton MCP server via subprocess and capture ALL output."""
import asyncio
import json
import sys
import subprocess
from datetime import datetime

async def test_mcp_subprocess():
    # Get the Maton API key from DB
    from app.database import AsyncSessionLocal
    from app.models.tool import Tool
    from app.core.security import decrypt_value
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tool).where(Tool.source == 'maton'))
        tools = result.scalars().all()

        if not tools:
            print("No Maton tools found")
            return

        t = tools[0]
        config = dict(t.config)
        raw_key = config.get('api_token') or config.get('api_key', '')

        try:
            decrypted = decrypt_value(raw_key)
            print(f"Decrypted API key: {decrypted[:10]}...")
        except Exception as e:
            print(f"Decrypt error: {e}")
            return

        app = config.get("app", "google-sheet")
        print(f"\n{'='*60}")
        print(f"App: {app}")
        print(f"Using npx to start @maton/mcp with app={app}")
        print(f"{'='*60}\n")

    # Build the MCP server command
    cmd = [
        "npx.cmd",
        "-y",
        "@maton/mcp",
        app,
        "--agent",
        f"--api-key={decrypted}"
    ]

    cmd_str = ' '.join(cmd)
    print(f"[{datetime.now().isoformat()}] Starting subprocess: {cmd_str}\n")

    # Create subprocess using standard subprocess module
    # Use shell=True on Windows for .cmd files
    proc = subprocess.Popen(
        cmd_str,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        bufsize=0,
        shell=True,  # Required on Windows for .cmd files
    )

    print(f"[{datetime.now().isoformat()}] Subprocess started with PID: {proc.pid}\n")

    # Create tasks for reading stdout and stderr
    async def read_stream(stream, prefix):
        """Read from stream and print with prefix."""
        loop = asyncio.get_event_loop()
        while True:
            data = await loop.run_in_executor(None, stream.read, 4096)
            if not data:
                break
            try:
                text = data.decode('utf-8', errors='replace')
                print(f"[{prefix}] {text.rstrip()}")
            except Exception as e:
                print(f"[{prefix}] Decode error: {e}")

    # Send MCP initialize request
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "clientInfo": {
                "name": "ocin-test",
                "version": "1.0.0"
            }
        }
    }

    init_json = json.dumps(initialize_request)
    print(f"[{datetime.now().isoformat()}] Sending MCP initialize request ({len(init_json)} bytes)...\n")

    proc.stdin.write(init_json.encode('utf-8'))
    proc.stdin.flush()

    # Wait a bit for initialize response
    await asyncio.sleep(3)

    # Send initialized notification
    initialized_notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }

    init_notif_json = json.dumps(initialized_notif)
    print(f"[{datetime.now().isoformat()}] Sending initialized notification ({len(init_notif_json)} bytes)...\n")

    proc.stdin.write(init_notif_json.encode('utf-8'))
    proc.stdin.flush()

    # Wait a bit for tools/list response
    await asyncio.sleep(3)

    # Send tools/list request
    tools_list_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list"
    }

    tools_list_json = json.dumps(tools_list_request)
    print(f"[{datetime.now().isoformat()}] Sending tools/list request ({len(tools_list_json)} bytes)...\n")

    proc.stdin.write(tools_list_json.encode('utf-8'))
    proc.stdin.flush()

    # Wait for output (20 second timeout)
    try:
        await asyncio.wait_for(
            asyncio.gather(
                read_stream(proc.stdout, 'STDOUT'),
                read_stream(proc.stderr, 'STDERR')
            ),
            timeout=20.0
        )
    except asyncio.TimeoutError:
        print(f"[{datetime.now().isoformat()}] TIMEOUT after 20 seconds")

    # Terminate subprocess
    print(f"\n[{datetime.now().isoformat()}] Terminating subprocess...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"[{datetime.now().isoformat()}] Force killing subprocess...")
        proc.kill()

    print(f"[{datetime.now().isoformat()}] Done\n")

if __name__ == "__main__":
    asyncio.run(test_mcp_subprocess())
