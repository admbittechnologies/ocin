import asyncio
import subprocess
import json

MATON_KEY = "GFxw--Qmh_fTvOAtjLlgH-XuKibQUw6xBlnX3LyEAl59Qg1ISdXHdaeb52WlUisuB0TEBsuM4UZuoQG7vqzCNS6ZJ9wJMXMK48E"
APP = "google-sheet"

async def test():
    proc = await asyncio.create_subprocess_exec(
        "npx", "-y", "@maton/mcp", APP, "--actions=all", f"--api-key={MATON_KEY}",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Read stderr in background
    async def read_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            print(f"[STDERR] {line.decode().strip()}")

    asyncio.create_task(read_stderr())

    # Wait for server to start
    await asyncio.sleep(4)

    def make_frame(obj):
        msg = json.dumps(obj)
        return f"Content-Length: {len(msg.encode())}\r\n\r\n{msg}".encode()

    # Send initialize
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "1.0"}}
    }))
    await proc.stdin.drain()
    await asyncio.sleep(1)

    # Send initialized notification
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "id": 2, "method": "notifications/initialized", "params": {}
    }))
    await proc.stdin.drain()
    await asyncio.sleep(1)

    # Send tools/list
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}
    }))
    await proc.stdin.drain()
    print("Waiting for tools/list response...")
    await asyncio.sleep(3)

    # Read response
    try:
        stdout_data = await asyncio.wait_for(proc.stdout.read(4096), timeout=2)
        print(f"[STDOUT tools/list]: {stdout_data.decode()}")
    except asyncio.TimeoutError:
        print("[STDOUT] Timeout waiting for tools/list")

    # Call google-sheet_check_connection
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {
            "name": "google-sheet_check_connection",
            "arguments": {}
        }
    }))
    await proc.stdin.drain()
    print("Called google-sheet_check_connection, waiting for response...")
    await asyncio.sleep(5)

    # Read response
    try:
        stdout_data = await asyncio.wait_for(proc.stdout.read(4096), timeout=5)
        print(f"[STDOUT check_connection]: {stdout_data.decode()}")
    except asyncio.TimeoutError:
        print("[STDOUT] Timeout waiting for check_connection")

    # Call google-sheet_create_spreadsheet
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {
            "name": "google-sheet_create_spreadsheet",
            "arguments": {"title": "OCIN_Direct_Test"}
        }
    }))
    await proc.stdin.drain()
    print("Called google-sheet_create_spreadsheet, waiting for response...")
    await asyncio.sleep(5)

    # Read response
    try:
        stdout_data = await asyncio.wait_for(proc.stdout.read(4096), timeout=5)
        print(f"[STDOUT create_spreadsheet]: {stdout_data.decode()}")
    except asyncio.TimeoutError:
        print("[STDOUT] Timeout waiting for create_spreadsheet")

if __name__ == "__main__":
    asyncio.run(test())
