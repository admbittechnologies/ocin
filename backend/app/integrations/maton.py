import logging
import hashlib
import hmac
from typing import Any

import httpx

logger = logging.getLogger("ocin")


class MatonClient:
    """Client for Maton.ai webhook integration."""

    TIMEOUT = 30.0

    def __init__(self, webhook_url: str, webhook_secret: str):
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.client = httpx.AsyncClient(timeout=self.TIMEOUT)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    def _generate_signature(self, payload: str) -> str:
        """Generate HMAC-SHA256 signature for the payload."""
        return hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def trigger_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Trigger a Maton workflow via webhook.

        Args:
            payload: The payload to send to the webhook

        Returns:
            The response from Maton

        Raises:
            ValueError: If webhook execution fails
        """
        import json

        json_payload = json.dumps(payload)
        signature = self._generate_signature(json_payload)

        try:
            response = await self.client.post(
                self.webhook_url,
                headers={
                    "Content-Type": "application/json",
                    "X-Maton-Signature": signature,
                },
                content=json_payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error({"event": "maton_trigger_workflow", "error": str(e)})
            raise ValueError(f"Maton webhook failed: {e.response.status_code}")
        except Exception as e:
            logger.error({"event": "maton_trigger_workflow", "error": str(e)})
            raise ValueError(f"Failed to trigger Maton workflow: {str(e)}")
