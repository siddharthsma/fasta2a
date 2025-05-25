# Library imports
import asyncio
import json
from typing import Any, Dict
from nats.aio.client import Client as NATS

# Local imports

class NATSClient:
    def __init__(self, server_url: str = "nats://localhost:4222"):
        self.server_url = server_url
        self.nats = NATS()
        self._connected = False

    async def connect(self) -> None:
        """Establishes an asynchronous connection to the NATS server."""
        if not self._connected:
            try:
                # Use the current running loop by default
                await self.nats.connect(self.server_url)
                self._connected = True
            except Exception as e:
                pass

    async def publish(self, subject: str, payload: Dict[str, Any]) -> None:
        """Publishes a JSON-encoded message to a NATS subject, auto-connecting if needed."""
        if not self._connected:
            # Ensure connection before publishing
            await self.connect()

        try:
            data = json.dumps(payload).encode()
            await self.nats.publish(subject, data)
        except Exception as e:
            print(f"Failed to publish message: {e}")
            raise

    async def close(self) -> None:
        """Close NATS connection gracefully"""
        if self._connected:
            await self.nats.close()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected