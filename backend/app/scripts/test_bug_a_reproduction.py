#!/usr/bin/env python3
"""
Test script for Bug A reproduction: SSE rendering bug.

This test attempts to reproduce the bug where on a multimodal turn, the chat UI
renders the previous turn's reply text even though the DB stores the correct new reply.

Reproduction recipe:
1. Send image X + question in a fresh thread. Wait for full reply.
2. Immediately send image Y + question (within ~5 seconds).
3. Check whether messages.content for turn 2's assistant_message contains Y's description.
"""

import os
import sys
import json
import base64
import asyncio
import httpx
from pathlib import Path

# Configuration
BASE_URL = os.getenv("OCIN_BASE_URL", "http://localhost:8000/api/v1")
EMAIL = os.getenv("OCIN_EMAIL", "test@example.com")
PASSWORD = os.getenv("OCIN_PASSWORD", "password")
AGENT_ID = os.getenv("OCIN_AGENT_ID", "")


async def authenticate():
    """Authenticate and get JWT token."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{BASE_URL}/auth/login",
            json={"email": EMAIL, "password": PASSWORD}
        )
        response.raise_for_status()
        data = response.json()
        return data["access_token"]


async def send_chat_message(token, agent_id, message, attachments=None, thread_id=None):
    """Send a chat message."""
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "agent_id": agent_id,
            "message": message,
        }
        if attachments:
            payload["attachments"] = attachments
        if thread_id:
            payload["thread_id"] = thread_id

        response = await client.post(
            f"{BASE_URL}/chat/send",
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        return response.json()


async def stream_chat_response(token, run_id):
    """Stream chat response via SSE."""
    url = f"{BASE_URL}/chat/stream?message_id={run_id}&token={token}"

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()

            full_text = ""
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line != "data: ":
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "token":
                            full_text += data.get("token", "")
                        elif data.get("type") == "done":
                            break
                    except json.JSONDecodeError:
                        continue

            return full_text


async def main():
    """Main test execution."""
    if not AGENT_ID:
        print("Error: OCIN_AGENT_ID environment variable is required")
        sys.exit(1)

    print("🔐 Authenticating...")
    token = await authenticate()
    print("✅ Authentication successful")

    # Create two different test images
    # Image 1: 1x1 red pixel PNG
    red_pixel = base64.b64encode(
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0'
        b'\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    ).decode('utf-8')

    # Image 2: 1x1 blue pixel PNG
    blue_pixel = base64.b64encode(
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0'
        b'\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb5\x00\x00\x00\x00IEND\xaeB`\x82'
    ).decode('utf-8')

    print("\n📸 Test 1: Send first image (red pixel)")
    response1 = await send_chat_message(
        token,
        AGENT_ID,
        "What color is this pixel?",
        attachments=[{
            "name": "red_pixel.png",
            "type": "image/png",
            "data_base64": red_pixel
        }]
    )
    print(f"✅ Message 1 sent: {response1['message_id']}")
    thread_id = response1.get('thread_id')

    # Stream the response and wait for completion
    print("⏳ Waiting for response 1...")
    reply1 = await stream_chat_response(token, response1['message_id'])
    print(f"📝 Reply 1: {reply1[:100]}...")
    print(f"   Expected: Should mention 'red'")

    # Small delay to ensure first response is complete
    await asyncio.sleep(1)

    print("\n📸 Test 2: Send second image immediately (blue pixel)")
    response2 = await send_chat_message(
        token,
        AGENT_ID,
        "What color is this pixel now?",
        attachments=[{
            "name": "blue_pixel.png",
            "type": "image/png",
            "data_base64": blue_pixel
        }],
        thread_id=thread_id
    )
    print(f"✅ Message 2 sent: {response2['message_id']}")

    # Stream the response
    print("⏳ Waiting for response 2...")
    reply2 = await stream_chat_response(token, response2['message_id'])
    print(f"📝 Reply 2: {reply2[:100]}...")
    print(f"   Expected: Should mention 'blue'")

    # Check for Bug A
    print("\n🔍 Analyzing results for Bug A...")

    # Check if both responses are distinct
    if "red" in reply1.lower() and "blue" in reply2.lower():
        print("✅ No Bug A detected: Both responses are correct and distinct")
        print("   Reply 1 mentions 'red'")
        print("   Reply 2 mentions 'blue'")
    elif "red" in reply1.lower() and "red" in reply2.lower():
        print("❌ Potential Bug A: Reply 2 mentions 'red' when it should mention 'blue'")
        print("   This could indicate SSE buffer contamination")
    elif "blue" in reply1.lower() and "blue" in reply2.lower():
        print("⚠️  Unexpected: Reply 1 mentions 'blue'")
    else:
        print("⚠️  Could not determine from responses")

    print("\n📋 Instructions for manual verification:")
    print("   1. Check the database for the messages in this thread")
    print("   2. Verify that messages.content for turn 2's assistant_message matches Reply 2 above")
    print("   3. If the database contains 'blue' but the UI shows 'red', Bug A is confirmed")
    print(f"   4. Thread ID: {thread_id}")


if __name__ == "__main__":
    asyncio.run(main())
