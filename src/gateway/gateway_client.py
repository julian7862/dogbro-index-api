"""Gateway client for WebSocket communication.

This module provides a clean abstraction over Socket.IO client,
following Single Responsibility Principle.
"""

import socketio
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayConfig:
    """Gateway configuration."""
    url: str
    reconnection: bool = True
    reconnection_delay: int = 1000


class GatewayClient:
    """Socket.IO client wrapper for gateway communication.

    Responsibilities:
    - Manage Socket.IO connection lifecycle
    - Emit events to gateway
    - Handle connection events
    """

    def __init__(self, config: GatewayConfig):
        """Initialize Gateway client.

        Args:
            config: Gateway configuration
        """
        self._config = config
        self._client: Optional[socketio.Client] = None
        self._connected = False

    def connect(self) -> None:
        """Establish connection to gateway server.

        Raises:
            ConnectionError: If connection fails
        """
        if self._connected:
            return

        self._client = socketio.Client()
        self._setup_event_handlers()

        try:
            self._client.connect(self._config.url)
            self._connected = True
            self._log(f"Connected to gateway at {self._config.url}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to gateway: {e}")

    def disconnect(self) -> None:
        """Disconnect from gateway server."""
        if self._client and self._connected:
            self._client.disconnect()
            self._connected = False
            self._log("Disconnected from gateway")

    def emit(self, event: str, data: Dict[str, Any]) -> None:
        """Emit event to gateway.

        Args:
            event: Event name
            data: Event data
        """
        if not self._connected or not self._client:
            self._log(f"Cannot emit {event}: Not connected", level="warning")
            return

        try:
            # Add timestamp if not present
            if 'timestamp' not in data:
                data['timestamp'] = datetime.now().isoformat()

            self._client.emit(event, data)
            self._log(f"Emitted event: {event}")
        except Exception as e:
            self._log(f"Failed to emit {event}: {e}", level="error")

    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            True if connected, False otherwise
        """
        return self._connected

    def _setup_event_handlers(self) -> None:
        """Setup Socket.IO event handlers."""
        if not self._client:
            return

        @self._client.event
        def connect():
            self._on_connect()

        @self._client.event
        def disconnect():
            self._on_disconnect()

        @self._client.on('*')
        def catch_all(event, data):
            self._on_event(event, data)

    def _on_connect(self) -> None:
        """Handle connection event."""
        self._connected = True
        self._log("Socket.IO connection established")
        self.emit('python_status', {'status': 'connected'})

    def _on_disconnect(self) -> None:
        """Handle disconnection event."""
        self._connected = False
        self._log("Socket.IO connection closed")

    def _on_event(self, event: str, data: Any) -> None:
        """Handle incoming events from gateway.

        Args:
            event: Event name
            data: Event data
        """
        self._log(f"Received event '{event}': {data}")

    def _log(self, message: str, level: str = "info") -> None:
        """Log message with timestamp.

        Args:
            message: Log message
            level: Log level (info, warning, error)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{timestamp}] [Gateway]"

        if level == "error":
            print(f"{prefix} ERROR: {message}")
        elif level == "warning":
            print(f"{prefix} WARNING: {message}")
        else:
            print(f"{prefix} {message}")
