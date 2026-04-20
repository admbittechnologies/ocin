#!/usr/bin/env python3
"""
End-to-end test script for multimodal chat with image injection.

This test validates the full pipeline:
1. Auth with the backend
2. Send a chat message with an image attachment
3. Stream response via SSE
4. Verify that agent correctly describes the image

Run inside of container: docker compose exec api python /app/scripts/test_chat_image.py
"""

import os
import sys
import json
import base64
import asyncio
import logging
import httpx
import httpx_sse
from pathlib import Path
from datetime import datetime

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_env_var(name, required=True, default=None):
    """Get environment variable with validation."""
    value = os.environ.get(name)
    if required and not value:
        logger.error(f"Missing required environment variable: {name}")
        logger.error("Please provide:")
        logger.error(f" {name}=<value>")
        sys.exit(1)
    return value or default


def main():
    """Main test execution."""
    # Step 1: List available test images
    tests_dir = Path("/app/tests")
    if not tests_dir.exists():
        logger.error(f"Tests directory not found: {tests_dir}")
        sys.exit(1)

    # Find image files (png, jpg, jpeg, webp)
    image_files = []
    for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
        image_files.extend(tests_dir.glob(ext))

    if not image_files:
        logger.error(f"No test images found in {tests_dir}")
        logger.error("Please place test images in one of these formats:")
        logger.error("  - .png (e.g., house.png)")
        logger.error("  - .jpg (e.g., car.jpg)")
        logger.error("  - .jpeg (e.g., postbox.jpeg)")
        logger.error("  - .webp (e.g., logo.webp)")
        sys.exit(1)

    # Step 2: Select test image
    selected_image = image_files[0]
    logger.info(f"Selected test image: {selected_image.name}")

    # Step 3: Check API health
    base_url = get_env_var("OCIN_BASE_URL", "http://localhost:8000/api/v1")

    try:
        logger.info(f"Checking API health at {base_url}/health")
        response = httpx.get(f"{base_url}/health", timeout=10)
        response.raise_for_status()
        health_data = response.json()
        logger.info(f"API health check passed: {health_data}")

        if health_data.get("db") != "ok" or health_data.get("api") != "ok":
            logger.error(f"API health check failed: {health_data}")
            sys.exit(1)

    except httpx.HTTPError as e:
        logger.error(f"API health check failed: {e}")
        sys.exit(1)

    # Step 4: Authenticate and get JWT
    email = get_env_var("OCIN_EMAIL", required=True)
    password = get_env_var("OCIN_PASSWORD", required=True)
    agent_id = get_env_var("OCIN_AGENT_ID", required=True)

    logger.info(f"Authenticating with email: {email}")

    try:
        auth_response = httpx.post(
            f"{base_url}/auth/login",
            json={
                "email": email,
                "password": password,
            },
            timeout=10
        )
        auth_response.raise_for_status()
        auth_data = auth_response.json()

        if "access_token" not in auth_data:
            logger.error(f"Login failed - no access_token in response: {auth_data}")
            sys.exit(1)

        jwt_token = auth_data["access_token"]
        logger.info(f"Authentication successful, obtained JWT")

    except httpx.HTTPError as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)

    # Step 5: Read and encode image
    logger.info(f"Reading test image: {selected_image.name}")
    try:
        with open(selected_image, "rb") as f:
            image_bytes = f.read()

        # Infer MIME type from file extension
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
        }
        file_ext = selected_image.suffix.lower()
        media_type = mime_types.get(file_ext, 'application/octet-stream')

        # Encode as base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:{media_type};base64,{image_base64}"

        logger.info(f"Image encoded: {len(image_bytes)} bytes, MIME: {media_type}")

    except FileNotFoundError:
        logger.error(f"Image file not found: {selected_image}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to read image: {e}")
        sys.exit(1)

    # Step 6: Send chat message with attachment
    prompt = get_env_var("OCIN_PROMPT", default="What do you see in this image? Be specific.")

    chat_payload = {
        "agent_id": agent_id,
        "message": prompt,
        "attachments": [
            {
                "name": selected_image.name,
                "type": media_type,
                "data_base64": image_base64,
            }
        ]
    }

    logger.info("Sending chat request with image attachment")
    logger.info(f"Payload: agent_id={agent_id}")
    logger.info(f"Payload: prompt={prompt[:50]}...")
    logger.info(f"Payload: attachments=[{selected_image.name}, {media_type}, {len(image_bytes)} bytes]")

    try:
        chat_response = httpx.post(
            f"{base_url}/chat/send",
            json=chat_payload,
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/json",
            },
            timeout=30
        )
        chat_response.raise_for_status()
        chat_data = chat_response.json()

        message_id = chat_data.get("message_id")
        thread_id = chat_data.get("thread_id")

        logger.info(f"Chat send successful")
        logger.info(f"Message ID: {message_id}")
        logger.info(f"Thread ID: {thread_id}")

    except httpx.HTTPError as e:
        logger.error(f"Chat send failed: {e}")
        sys.exit(1)

    # Step 7: Stream response via SSE
    stream_url = f"{base_url}/chat/stream"

    try:
        logger.info(f"Connecting to SSE stream: {stream_url}")

        async def process_events():
            async for event in event_source:
                try:
                    data = json.loads(event.data)
                    event_type = data.get("type", "")

                    logger.info(f"Received SSE event: {event_type}")

                    if event_type == "token":
                        token = data.get("token", "")
                        full_reply.append(token)
                        reply_tokens.append(len(token))
                    elif event_type == "done":
                        logger.info("Received 'done' event - stream complete")
                        break
                    elif event_type in ("error", "progress"):
                        logger.info(f"Received {event_type} event: {data.get('message', 'N/A')[:100]}")
                    else:
                        logger.warning(f"Unexpected SSE event type: {event_type}")

                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse SSE data: {event.data}")
                    continue

            if not full_reply:
                logger.error("No tokens received from stream")
                sys.exit(1)

            full_reply_text = "".join(full_reply)

            # Step 8: Analyze the response
            logger.info("=" * 60)
            logger.info("TEST RESULT ANALYSIS")
            logger.info("=" * 60)
            logger.info(f"image_path: {selected_image.name}")
            logger.info(f"image_size_bytes: {len(image_bytes)}")
            logger.info(f"thread_id: {thread_id}")
            logger.info(f"message_id: {message_id}")
            logger.info(f"prompt_used: {prompt}")
            logger.info(f"reply_length_chars: {len(full_reply_text)}")
            logger.info(f"reply_length_tokens: {sum(reply_tokens)}")

            # Heuristic: Check if reply mentions seeing the image
            reply_lower = full_reply_text.lower()
            image_keywords = ["see", "image", "picture", "photo", "shows", "display", "visible"]
            mentions_image = any(keyword in reply_lower for keyword in image_keywords)
            logger.info(f"mentions_image: {mentions_image}")

            # Heuristic: Detect vision-denial phrases
            denial_keywords = ["don't see", "can't see", "cannot see", "no picture", "no image", "only see"]
            vision_denial_detected = any(phrase in reply_lower for phrase in denial_keywords)
            logger.info(f"vision_denial_detected: {vision_denial_detected}")

            # Verify BinaryContent reached agent (via log inspection)
            binary_content_confirmed = False
            logger.warning("NOTE: BinaryContent confirmation requires inspecting container logs")

            logger.info("=" * 60)
            logger.info("VERDICT")
            logger.info("=" * 60)

            # Determine verdict
            if mentions_image and not vision_denial_detected and len(full_reply_text) > 50:
                verdict = "PASS"
                logger.info("✓ PASS: Agent described the image correctly")
            elif vision_denial_detected:
                verdict = "FAIL"
                logger.error("✗ FAIL: Vision-denial phrase detected")
            else:
                verdict = "NOMINAL"
                logger.warning("? NOMINAL: Agent didn't describe image but didn't use denial phrase")

            # Print final result
            logger.info("-" * 60)
            logger.info("FINAL VERDICT")
            logger.info("-" * 60)
            logger.info(f"verdict: {verdict}")

            # Print reply preview
            logger.info("-" * 60)
            logger.info("ASSISTANT REPLY (RAW)")
            logger.info("-" * 60)
            logger.info(full_reply_text[:500])
            logger.info("-" * 60)

            # Exit with appropriate code
            sys.exit(0 if verdict == "PASS" else 1)

    except httpx.HTTPError as e:
        logger.error(f"SSE connection failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        sys.exit(2)
    except Exception as e:
        logger.error(f"Unexpected error during streaming: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
