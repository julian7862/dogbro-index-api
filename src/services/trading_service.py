"""Trading service that integrates Gateway and Shioaji clients.

This module orchestrates communication between Gateway and Shioaji,
following Single Responsibility and Dependency Inversion Principles.
"""

import time
from datetime import datetime
from typing import Optional

from src.gateway.gateway_client import GatewayClient
from src.trading.shioaji_client import ShioajiClient


class TradingService:
    """Trading service orchestrator.

    Responsibilities:
    - Coordinate Gateway and Shioaji clients
    - Emit trading events to gateway
    - Run main event loop
    - Handle graceful shutdown
    """

    def __init__(
        self,
        gateway_client: GatewayClient,
        shioaji_client: ShioajiClient,
        heartbeat_interval: int = 10
    ):
        """Initialize Trading Service.

        Args:
            gateway_client: Gateway client instance
            shioaji_client: Shioaji client instance
            heartbeat_interval: Heartbeat interval in seconds
        """
        self._gateway = gateway_client
        self._shioaji = shioaji_client
        self._heartbeat_interval = heartbeat_interval
        self._running = False

    def start(self) -> None:
        """Start the trading service.

        This will:
        1. Connect to Gateway
        2. Connect to Shioaji
        3. Emit ready status
        4. Start main loop

        Raises:
            RuntimeError: If service is already running
            ConnectionError: If connection fails
        """
        if self._running:
            raise RuntimeError("Service is already running")

        try:
            # Step 1: Connect to Gateway
            self._log("Starting trading service...")
            self._gateway.connect()

            # Step 2: Connect to Shioaji
            self._shioaji.connect()

            # Step 3: Emit ready status
            self._emit_ready_status()

            # Step 4: Start main loop
            self._running = True
            self._log("Trading service started successfully")
            self._run_main_loop()

        except KeyboardInterrupt:
            self._log("Received shutdown signal")
            self.stop()
        except Exception as e:
            self._log(f"Service error: {e}", level="error")
            self._emit_error(str(e))
            self.stop()
            raise

    def stop(self) -> None:
        """Stop the trading service gracefully."""
        if not self._running:
            return

        self._log("Stopping trading service...")
        self._running = False

        # Disconnect clients
        self._shioaji.disconnect()
        self._gateway.disconnect()

        self._log("Trading service stopped")

    def is_running(self) -> bool:
        """Check if service is running.

        Returns:
            True if running, False otherwise
        """
        return self._running

    def _run_main_loop(self) -> None:
        """Run main event loop with heartbeat."""
        self._log("Main loop started. Press Ctrl+C to exit.")

        while self._running:
            try:
                time.sleep(self._heartbeat_interval)
                self._send_heartbeat()
            except KeyboardInterrupt:
                break
            except Exception as e:
                self._log(f"Loop error: {e}", level="error")
                self._emit_error(str(e))

    def _emit_ready_status(self) -> None:
        """Emit ready status to gateway."""
        self._gateway.emit('shioaji_ready', {
            'status': 'ready',
            'simulation': True,
            'version': self._shioaji.get_version()
        })
        self._log("Emitted ready status")

    def _send_heartbeat(self) -> None:
        """Send heartbeat to gateway."""
        self._gateway.emit('heartbeat', {
            'status': 'running',
            'shioaji_connected': self._shioaji.is_connected(),
            'gateway_connected': self._gateway.is_connected()
        })

    def _emit_error(self, error: str) -> None:
        """Emit error to gateway.

        Args:
            error: Error message
        """
        if self._gateway.is_connected():
            self._gateway.emit('python_error', {
                'error': error
            })

    def _log(self, message: str, level: str = "info") -> None:
        """Log message with timestamp.

        Args:
            message: Log message
            level: Log level (info, warning, error)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{timestamp}] [TradingService]"

        if level == "error":
            print(f"{prefix} ERROR: {message}")
        elif level == "warning":
            print(f"{prefix} WARNING: {message}")
        else:
            print(f"{prefix} {message}")
