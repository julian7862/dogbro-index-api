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

        # 設定 logging
        self._logger = self._setup_logger()

    def connect(self) -> None:
        """Establish connection to gateway server with auto-reconnection.

        Raises:
            ConnectionError: If connection fails
        """
        if self._connected:
            return

        # 建立 Socket.IO Client 並啟用自動重連機制
        self._client = socketio.Client(
            reconnection=self._config.reconnection,
            reconnection_attempts=0,  # 無限重試
            reconnection_delay=1,  # 初始延遲 1 秒
            reconnection_delay_max=10,  # 最大延遲 10 秒
            randomization_factor=0.5  # 加入隨機因子避免同時重連
        )
        self._setup_event_handlers()

        try:
            self._log(f"正在連接到 Gateway: {self._config.url}")
            self._client.connect(self._config.url)
            self._connected = True
            self._log(f"已連接到 Gateway: {self._config.url}")
        except Exception as e:
            raise ConnectionError(f"連接 Gateway 失敗: {e}")

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
        self._logger.info("Socket.IO 連線已建立")
        self.emit('python_status', {'status': 'connected'})

    def _on_disconnect(self) -> None:
        """Handle disconnection event."""
        self._connected = False
        self._logger.warning("Socket.IO 連線已中斷（將自動重連）")

    def _on_event(self, event: str, data: Any) -> None:
        """Handle incoming events from gateway.

        Args:
            event: Event name
            data: Event data
        """
        self._log(f"Received event '{event}': {data}")

    def _setup_logger(self):
        """設定 logger"""
        import logging
        logger = logging.getLogger(f"{__name__}.GatewayClient")
        return logger

    def _log(self, message: str, level: str = "info") -> None:
        """Log message with timestamp.

        Args:
            message: Log message
            level: Log level (info, warning, error)
        """
        if level == "error":
            self._logger.error(message)
        elif level == "warning":
            self._logger.warning(message)
        else:
            self._logger.info(message)
