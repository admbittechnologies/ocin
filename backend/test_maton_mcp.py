import asyncio
import subprocess
import json
import struct

MATON_KEY = "GFxw--Qmh_fTvOAtjLlgH-XuKibQUw6xBlnX3LyEAl59Qg1ISdXHdaeb52WlUisuB0TEBsuM4UZuoQG7vqzCNS6ZJ9wJMXMK48E"
APP = "google-sheet"

async def send_request(proc, req_id, method, params=None):
    """Send a JSON-RPC request with proper framing."""
    if params is None:
        params = {}

    request = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params
    }

    body = json.dumps(request, separators=(',', ':'))
    message = f"Content-Length: {len(body)}\r\n\r\n{body}"

    proc.stdin.write(message.encode())
    await proc.stdin.drain()

async def read_stdout_until(expected_count=1):
    """Read JSON-RPC responses until we get expected_count messages."""
    responses = []
    buffer = b""

    for _ in range(expected_count):
        try:
            while True:
                data = await proc.stdout.read(1024)
                if not data:
                    break
                buffer += data

                # Look for complete JSON-RPC messages
                lines = buffer.split(b'\r\n\r\n')
                if len(lines) >= 2:
                    # We have at least one complete message
                    # Process all complete messages
                    for i in range(len(lines) - 1):
                        header = lines[i].decode().strip()
                        if header.startswith("Content-Length:"):
                            # This is the header, skip it
                            continue

                        # Next line is the body
                        if i + 1 < len(lines):
                            body = lines[i + 1].decode().strip()
                            try:
                                responses.append(json.loads(body))
                            except json.JSONDecodeError as e:
                                print(f"[ERROR parsing JSON]: {e}")
                            break

                    # Clear processed messages from buffer
                    buffer = b"".join(lines[len(lines)-1:])

                # Break if we got a message
                if responses:
                    break

        except asyncio.TimeoutError:
            print(f"[TIMEOUT waiting for response {len(responses)+1}")
            break

    return responses

async def main():
    # Start the MCP server process
    proc = await asyncio.create_subprocess_exec(
        ["npx", "-y", "@maton/mcp", APP, "--actions=all", f"--api-key={MATON_KEY}"],
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    print("[INFO] Starting MCP server...")

    # Wait for server to be ready (npx prints a message)
    await asyncio.sleep(3)

    # Step 1: Initialize
    await send_request(proc, 1, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "ocin-test", "version": "1.0"}
    })
    print("[INFO] Sent initialize request")

    # Read initialize response
    init_responses = await read_stdout_until(1)
    if init_responses:
        print(f"[INFO] Initialize response: {json.dumps(init_responses, indent=2)}")
    else:
        print("[ERROR] No initialize response")
        return

    # Step 2: Send initialized notification
    await send_request(proc, 2, "notifications/initialized")
    print("[INFO] Sent initialized notification")

    # Step 3: List tools
    await send_request(proc, 3, "tools/list")
    print("[INFO] Sent tools/list request")

    # Read tools/list response
    tools_responses = await read_stdout_until(1)
    if tools_responses:
        print(f"[INFO] Tools listed: {json.dumps(tools_responses, indent=2)}")

        # Extract tool names from the response
        if tools_responses and "result" in tools_responses[0]:
            tools = tools_responses[0]["result"].get("tools", [])
            print(f"[INFO] Available tools ({len(tools)}):")
            for tool in tools:
                print(f"  - {tool['name']}")
        else:
            print("[ERROR] Tools response doesn't contain 'result.tools'")
    else:
        print("[ERROR] No tools/list response")
        return

    # Step 4: Call check_connection
    await send_request(proc, 4, "tools/call", {
        "name": "google-sheet_check_connection",
        "arguments": {}
    })
    print("[INFO] Sent check_connection request")

    # Read check_connection response
    check_responses = await read_stdout_until(1)
    if check_responses:
        print(f"[INFO] check_connection response: {json.dumps(check_responses, indent=2)}")
    else:
        print("[ERROR] No check_connection response")
        return

    # Step 5: Call create_spreadsheet (skipping connection for direct test)
    await send_request(proc, 5, "tools/call", {
        "name": "google-sheet_create_spreadsheet",
        "arguments": {"title": "OCIN_Direct_Test"}
    })
    print("[INFO] Sent create_spreadsheet request")

    # Read create_spreadsheet response
    create_responses = await read_stdout_until(1)
    if create_responses:
        print(f"[INFO] create_spreadsheet response: {json.dumps(create_responses, indent=2)}")
    else:
        print("[ERROR] No create_spreadsheet response")
        return

    # Terminate
    proc.terminate()
    await asyncio.sleep(1)
    print("[INFO] Test complete")

if __name__ == "__main__":
    asyncio.run(main())
