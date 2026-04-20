import logging
from typing import Any

import httpx

logger = logging.getLogger("ocin")


class ComposioClient:
    """Client for Composio API integration."""

    BASE_URL = "https://api.composio.dev"
    TIMEOUT = 30.0

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=self.TIMEOUT)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def get_available_actions(self, connection_id: str) -> list[dict[str, Any]]:
        """
        Get available actions for a Composio connection.

        Args:
            connection_id: The Composio connection ID

        Returns:
            List of available actions with metadata

        Raises:
            ValueError: If connection is not found or invalid
        """
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/api/v1/connections/{connection_id}/actions",
                headers={"x-api-key": self.api_key},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error({"event": "composio_get_actions", "error": "Connection not found", "connection_id": connection_id})
                raise ValueError("Composio connection not found")
            elif e.response.status_code == 401:
                logger.error({"event": "composio_get_actions", "error": "Invalid API key"})
                raise ValueError("Invalid Composio API key")
            else:
                logger.error({"event": "composio_get_actions", "error": str(e)})
                raise ValueError(f"Composio API error: {e.response.status_code}")
        except Exception as e:
            logger.error({"event": "composio_get_actions", "error": str(e)})
            raise ValueError(f"Failed to fetch Composio actions: {str(e)}")

    async def execute_action(
        self,
        connection_id: str,
        action_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a Composio action.

        Args:
            connection_id: The Composio connection ID
            action_id: The ID of the action to execute
            params: Parameters for the action

        Returns:
            The result of the action execution

        Raises:
            ValueError: If execution fails
        """
        try:
            response = await self.client.post(
                f"{self.BASE_URL}/api/v1/actions/{action_id}/execute",
                headers={"x-api-key": self.api_key},
                json={
                    "connectionId": connection_id,
                    "params": params,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error({"event": "composio_execute_action", "error": str(e), "action_id": action_id})
            raise ValueError(f"Composio action execution failed: {e.response.status_code}")
        except Exception as e:
            logger.error({"event": "composio_execute_action", "error": str(e), "action_id": action_id})
            raise ValueError(f"Failed to execute Composio action: {str(e)}")
