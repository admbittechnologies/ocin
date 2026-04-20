import asyncio
import json
import sys

sys.path.insert(0, '/app')

async def get_maton_key():
    from app.database import AsyncSessionLocal
    from app.models.tool import Tool
    from app.core.security import decrypt_value
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tool).where(Tool.source == "maton"))
        tools = result.scalars().all()
        for t in tools:
            raw = t.config.get("api_key") or t.config.get("api_token", "")
            try:
                key = decrypt_value(raw)
                app = t.config.get("app", "google-sheet")
                print(f"[CONFIG] app={app} key_length={len(key)} key_preview={key[:10]}...")
                return key, app
            except Exception as e:
                print(f"[ERROR] decrypt failed: {e}")
    return None, None


async def test_mcp(maton_key, app):
    print(f"\n[STEP] Starting MCP server: npx @maton/mcp {app} --actions=all")

    proc = await asyncio.create_subprocess_exec(
        "npx", "-y", "@maton/mcp", app, "--actions=all", f"--api-key={maton_key}",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_chunks = []

    async def read_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            print(f"[STDERR] {line.decode().strip()}")

    async def read_stdout():
        buf = b""
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
            stdout_chunks.append(chunk.decode(errors="replace"))
            print(f"[STDOUT_RAW] {chunk.decode(errors='replace')!r}")

    stderr_task = asyncio.create_task(read_stderr())
    stdout_task = asyncio.create_task(read_stdout())

    await asyncio.sleep(5)
    print("[STEP] Server should be ready, sending MCP handshake...")

    def make_frame(obj):
        msg = json.dumps(obj)
        return f"Content-Length: {len(msg.encode())}\r\n\r\n{msg}".encode()

    # 1. initialize
    print("[SEND] initialize")
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ocin-test", "version": "1.0"}
        }
    }))
    await proc.stdin.drain()
    await asyncio.sleep(2)

    # 2. initialized notification
    print("[SEND] notifications/initialized")
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}
    }))
    await proc.stdin.drain()
    await asyncio.sleep(1)

    # 3. tools/list
    print("[SEND] tools/list")
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
    }))
    await proc.stdin.drain()
    await asyncio.sleep(3)

    # 4. check_connection
    tool_name = f"{app}_check_connection"
    print(f"[SEND] tools/call -> {tool_name}")
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": tool_name, "arguments": {}}
    }))
    await proc.stdin.drain()
    await asyncio.sleep(5)

    # 5. create_spreadsheet
    tool_name = f"{app}_create_spreadsheet"
    print(f"[SEND] tools/call -> {tool_name}")
    proc.stdin.write(make_frame({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": {"title": "OCIN_Direct_Test"}
        }
    }))
    await proc.stdin.drain()
    await asyncio.sleep(8)

    print("\n[STEP] Killing server and collecting output...")
    proc.kill()

    try:
        await asyncio.wait_for(stderr_task, timeout=2)
    except asyncio.TimeoutError:
        pass

    try:
        await asyncio.wait_for(stdout_task, timeout=2)
    except asyncio.TimeoutError:
        pass

    await proc.wait()

    print("\n========== FULL STDOUT ==========")
    full_stdout = "".join(stdout_chunks)
    if full_stdout.strip():
        print(full_stdout)
        # Try to parse individual JSON-RPC responses
        print("\n========== PARSED RESPONSES ==========")
        parts = full_stdout.split("Content-Length:")
        for part in parts:
            if not part.strip():
                continue
            try:
                json_start = part.find("{")
                if json_start >= 0:
                    obj = json.loads(part[json_start:].strip())
                    print(json.dumps(obj, indent=2))
                    print("---")
            except Exception:
                print(f"[RAW] {part[:200]}")
    else:
        print("[EMPTY] No stdout received from MCP server")

    print("\n========== DONE ==========")


async def main():
    print("======= Maton MCP Direct Test =======\n")
    maton_key, app = await get_maton_key()
    if not maton_key:
        print("[FATAL] Could not get Maton API key from database")
        return
    await test_mcp(maton_key, app)


asyncio.run(main())