import logging
from typing import Any

import httpx

logger = logging.getLogger("ocin")


class ApifyClient:
    """Client for Apify Actor integration."""

    BASE_URL = "https://api.apify.com/v2"
    TIMEOUT = 30.0
    POLL_INTERVAL = 10  # seconds
    MAX_POLL_TIME = 300  # 5 minutes
    MAX_DATASET_ITEMS = 50


    def __init__(self, api_token: str):
        self.api_token = api_token
        self.client = httpx.AsyncClient(timeout=self.TIMEOUT)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def run_actor(
        self,
        actor_id: str,
        input_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Run an Apify Actor and return dataset items.

        Args:
            actor_id: The ID of the Actor to run
            input_data: Input data for the Actor

        Returns:
            List of dataset items (max 50)

        Raises:
            TimeoutError: If Actor doesn't finish within MAX_POLL_TIME
            ValueError: If Actor execution fails
        """
        try:
            # Start the Actor run
            response = await self.client.post(
                f"{self.BASE_URL}/acts/{actor_id}/runs",
                headers={"Authorization": f"Bearer {self.api_token}"},
                json=input_data,
            )
            response.raise_for_status()
            run_data = response.json()
            run_id = run_data["data"]["id"]

            # Poll for completion
            from asyncio import sleep
            import time

            start_time = time.time()
            while time.time() - start_time < self.MAX_POLL_TIME:
                status_response = await self.client.get(
                    f"{self.BASE_URL}/actor-runs/{run_id}",
                    headers={"Authorization": f"Bearer {self.api_token}"},
                )
                status_response.raise_for_status()
                status_data = status_response.json()
                status = status_data["data"]["status"]

                if status == "SUCCEEDED":
                    # Fetch dataset items
                    dataset_id = status_data["data"]["defaultDatasetId"]
                    dataset_response = await self.client.get(
                        f"{self.BASE_URL}/datasets/{dataset_id}/items",
                        headers={"Authorization": f"Bearer {self.api_token}"},
                        params={"limit": self.MAX_DATASET_ITEMS},
                    )
                    dataset_response.raise_for_status()
                    return dataset_response.json().get("items", [])
                elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                    logger.error({"event": "apify_run_actor", "error": f"Actor {status}", "actor_id": actor_id, "run_id": run_id})
                    raise ValueError(f"Apify Actor run {status}")

                await sleep(self.POLL_INTERVAL)

            logger.error({"event": "apify_run_actor", "error": "Timeout", "actor_id": actor_id, "run_id": run_id})
            raise TimeoutError(f"Apify Actor did not complete within {self.MAX_POLL_TIME} seconds")

        except httpx.HTTPStatusError as e:
            logger.error({"event": "apify_run_actor", "error": str(e), "actor_id": actor_id})
            raise ValueError(f"Apify API error: {e.response.status_code}")
        except Exception as e:
            logger.error({"event": "apify_run_actor", "error": str(e), "actor_id": actor_id})
            raise ValueError(f"Failed to run Apify Actor: {str(e)}")
