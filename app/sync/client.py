import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pydantic import ValidationError

from app.sync.models import SyncManifest

logger = logging.getLogger("qdrant_edge.sync.client")


class SyncClient:
    """Client for communicating with the central catalog synchronization server."""

    def __init__(
        self,
        server_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
        api_key: Optional[str] = None,
    ):
        self.server_url = server_url.rstrip("/") if server_url else ""
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            headers = {"Accept": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            self._client = httpx.Client(
                timeout=self.timeout_seconds,
                headers=headers,
                follow_redirects=True,
            )
        return self._client

    def fetch_manifest(self, since_version: Optional[str] = None) -> Tuple[Optional[SyncManifest], Optional[str]]:
        """Retrieves sync manifest from central server. Never raises unhandled network exceptions."""
        if not self.server_url:
            return None, "Sync server URL is not configured."

        url = f"{self.server_url}/api/sync/manifest"
        params = {}
        if since_version:
            params["since"] = since_version

        try:
            client = self._get_client()
            response = client.get(url, params=params)
            if response.status_code != 200:
                msg = f"Central server returned status {response.status_code}: {response.text[:200]}"
                logger.warning(f"Failed to fetch manifest: {msg}")
                return None, msg

            data = response.json()
            manifest = SyncManifest(**data)
            return manifest, None

        except httpx.TimeoutException:
            msg = f"Timeout ({self.timeout_seconds}s) connecting to sync server at {url}"
            logger.warning(msg)
            return None, msg
        except httpx.RequestError as e:
            msg = f"Network connection error to sync server: {e}"
            logger.warning(msg)
            return None, msg
        except (ValueError, ValidationError) as e:
            msg = f"Malformed manifest response from sync server: {e}"
            logger.warning(msg)
            return None, msg
        except Exception as e:
            msg = f"Unexpected error during manifest fetch: {e}"
            logger.error(msg)
            return None, msg

    def fetch_experiences(self, ids: List[int]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetches full experience records for specific IDs. Never raises unhandled network exceptions."""
        if not ids:
            return [], None

        if not self.server_url:
            return [], "Sync server URL is not configured."

        url = f"{self.server_url}/api/sync/experiences"
        id_str = ",".join(str(i) for i in ids)

        try:
            client = self._get_client()
            response = client.get(url, params={"ids": id_str})
            if response.status_code != 200:
                msg = f"Central server returned status {response.status_code} fetching experiences: {response.text[:200]}"
                logger.warning(msg)
                return [], msg

            data = response.json()
            if isinstance(data, dict) and "experiences" in data:
                items = data["experiences"]
            elif isinstance(data, list):
                items = data
            else:
                items = []

            return items, None

        except httpx.TimeoutException:
            msg = f"Timeout ({self.timeout_seconds}s) fetching experiences from {url}"
            logger.warning(msg)
            return [], msg
        except httpx.RequestError as e:
            msg = f"Network connection error fetching experiences: {e}"
            logger.warning(msg)
            return [], msg
        except (ValueError, ValidationError) as e:
            msg = f"Malformed experience payload response: {e}"
            logger.warning(msg)
            return [], msg
        except Exception as e:
            msg = f"Unexpected error fetching experiences: {e}"
            logger.error(msg)
            return [], msg

    def close(self) -> None:
        """Closes underlying HTTP client session."""
        if self._client and not self._client.is_closed:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
