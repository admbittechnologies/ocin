"""
Test script to reproduce Bug A and capture diagnostic logs.

Sends an image attachment and monitors backend logs for SSE stream diagnostics.
"""
import asyncio
import json
import base64
import requests
import time
import sys
from pathlib import Path

# Configuration
API_BASE = "http://localhost:8000/api/v1"
AUTH_EMAIL = "admin@ocin.ai"  # Change if needed
AUTH_PASSWORD = "admin123"  # Change if needed

# Small test image (1x1 red PNG)
TEST_IMAGE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)


async def test_sse_stream_diagnosis():
    """Test SSE stream with image attachment and capture diagnostic logs."""

    # Step 1: Login to get JWT token
    print("🔐 Step 1: Logging in...")
    login_response = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": AUTH_EMAIL, "password": AUTH_PASSWORD}
    )

    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.text}")
        return False

    token = login_response.json()["access_token"]
    print(f"✅ Login successful, token: {token[:50]}...")

    # Step 2: Get list of agents
    print("\n🤖 Step 2: Getting available agents...")
    agents_response = requests.get(
        f"{API_BASE}/agents/",
        headers={"Authorization": f"Bearer {token}"}
    )

    if agents_response.status_code != 200:
        print(f"❌ Failed to get agents: {agents_response.text}")
        return False

    agents = agents_response.json()["agents"]
    if not agents:
        print("❌ No agents found")
        return False

    agent_id = agents[0]["id"]
    print(f"✅ Using agent: {agents[0]['name']} (id: {agent_id})")

    # Step 3: Send chat message with image attachment
    print("\n📸 Step 3: Sending image attachment...")
    payload = {
        "agent_id": agent_id,
        "message": "What do you see in this image?",
        "attachments": [
            {
                "name": "test.png",
                "type": "image/png",
                "data_base64": TEST_IMAGE_B64
            }
        ]
    }

    send_response = requests.post(
        f"{API_BASE}/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json=payload
    )

    if send_response.status_code != 200:
        print(f"❌ Failed to send message: {send_response.text}")
        return False

    result = send_response.json()
    message_id = result["message_id"]
    thread_id = result.get("thread_id")
    print(f"✅ Message sent (id: {message_id}, thread: {thread_id})")

    # Step 4: Open SSE stream and monitor events
    print("\n🔄 Step 4: Opening SSE stream...")
    print("=" * 60)
    print("SSE Stream Events:")
    print("=" * 60)

    stream_url = f"{API_BASE}/chat/stream?message_id={message_id}&token={token}"

    events_received = []
    last_event_time = time.time()
    timeout_seconds = 60  # 1 minute timeout

    try:
        with requests.get(stream_url, stream=True, timeout=timeout_seconds) as response:
            if response.status_code != 200:
                print(f"❌ SSE stream failed: {response.status_code} {response.text}")
                return False

            print(f"✅ SSE stream opened (status: {response.status_code})")

            for line in response.iter_lines(decode_unicode=True):
                if line:
                    current_time = time.time()
                    elapsed = current_time - last_event_time
                    last_event_time = current_time

                    # Parse SSE line
                    if line.startswith("event:"):
                        event_type = line.replace("event: ", "").strip()
                        print(f"\n[{elapsed:.2f}s] 📡 Event: {event_type}")
                    elif line.startswith("data:"):
                        try:
                            data = json.loads(line.replace("data: ", "").strip())
                            print(f"[{elapsed:.2f}s] 📦 Data: {data.get('type', 'unknown')}")

                            # Store events for summary
                            events_received.append({
                                "elapsed": elapsed,
                                "type": data.get("type"),
                                "data": data
                            })

                            # Stop if done
                            if data.get("type") == "done":
                                print(f"\n✅ Stream completed successfully!")
                                break

                            # Stop if error
                            if data.get("type") == "error":
                                print(f"\n❌ Stream error: {data.get('error')}")
                                break
                        except json.JSONDecodeError as e:
                            print(f"[{elapsed:.2f}s] ⚠️  Failed to parse data: {e}")

                    elif line.startswith(":"):
                        # Keepalive
                        continue

        print("\n" + "=" * 60)
        print("SSE Stream Summary:")
        print("=" * 60)
        print(f"Total events received: {len(events_received)}")
        print(f"Total time: {time.time() - last_event_time:.2f}s")

        # Event breakdown
        event_types = {}
        for event in events_received:
            event_type = event["type"]
            event_types[event_type] = event_types.get(event_type, 0) + 1

        print("\nEvent breakdown:")
        for event_type, count in event_types.items():
            print(f"  {event_type}: {count}")

        # Check for expected events
        has_connected = any(e["type"] == "connected" for e in events_received)
        has_token = any(e["type"] == "token" for e in events_received)
        has_done = any(e["type"] == "done" for e in events_received)
        has_error = any(e["type"] == "error" for e in events_received)

        print("\nExpected events check:")
        print(f"  connected: {'✅' if has_connected else '❌'}")
        print(f"  token: {'✅' if has_token else '❌'}")
        print(f"  done: {'✅' if has_done else '❌'}")
        print(f"  error: {'⚠️ ' if has_error else '✅ (none)'}")

        return True

    except requests.exceptions.ChunkedEncodingError as e:
        print(f"\n❌ ChunkedEncodingError: {e}")
        print("   This indicates ERR_INCOMPLETE_CHUNKED_ENCODING from the browser side!")
        print("   The server closed the connection without proper SSE termination.")
        return False
    except requests.exceptions.Timeout:
        print(f"\n❌ Request timeout after {timeout_seconds} seconds")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🚀 Bug A Diagnosis Test")
    print("=" * 60)
    print("\nThis test reproduces the SSE stream issue with image attachments.")
    print("It sends a tiny image and monitors the SSE stream for proper termination.")
    print("\nIMPORTANT: Monitor 'docker compose logs -f api' in a separate terminal")
    print("to capture the diagnostic logs from the backend.")
    print("\n" + "=" * 60)

    try:
        success = asyncio.run(test_sse_stream_diagnosis())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
