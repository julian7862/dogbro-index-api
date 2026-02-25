"""Shioaji API client wrapper.

This module provides a clean abstraction over Shioaji API,
following Single Responsibility Principle.
"""

import shioaji as sj
from dataclasses import dataclass
from typing import Optional, List, Any
from datetime import datetime


@dataclass(frozen=True)
class ShioajiConfig:
    """Shioaji API configuration."""
    api_key: str
    secret_key: str
    ca_cert_path: str
    ca_password: str
    simulation: bool = True


class ShioajiClient:
    """Shioaji API client wrapper.

    Responsibilities:
    - Manage Shioaji API lifecycle (login, logout)
    - Activate CA certificate
    - Provide access to trading operations
    """

    def __init__(self, config: ShioajiConfig):
        """Initialize Shioaji client.

        Args:
            config: Shioaji configuration
        """
        self._config = config
        self._api: Optional[sj.Shioaji] = None
        self._logged_in = False

    def connect(self) -> None:
        """Initialize and login to Shioaji API.

        Raises:
            ConnectionError: If login or CA activation fails
        """
        if self._logged_in:
            return

        try:
            self._log("Initializing Shioaji API...")
            self._api = sj.Shioaji(simulation=self._config.simulation)

            self._log("Logging in to Shioaji...")
            self._api.login(
                api_key=self._config.api_key,
                secret_key=self._config.secret_key,
                fetch_contract=False
            )
            self._log("Login successful")

            self._log("Activating CA certificate...")
            self._api.activate_ca(
                ca_path=self._config.ca_cert_path,
                ca_passwd=self._config.ca_password,
            )
            self._log("CA activation successful")

            self._logged_in = True

        except Exception as e:
            raise ConnectionError(f"Failed to connect to Shioaji: {e}")

    def disconnect(self) -> None:
        """Logout from Shioaji API."""
        if self._api and self._logged_in:
            try:
                self._log("Logging out from Shioaji...")
                self._api.logout()
                self._logged_in = False
                self._log("Logout successful")
            except Exception as e:
                self._log(f"Logout failed: {e}", level="error")

    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            True if logged in, False otherwise
        """
        return self._logged_in

    def get_api(self) -> Optional[sj.Shioaji]:
        """Get underlying Shioaji API instance.

        Returns:
            Shioaji API instance or None if not connected
        """
        return self._api if self._logged_in else None

    def get_contracts_sample(self, limit: int = 3) -> List[Any]:
        """Get sample contracts for testing.

        Args:
            limit: Number of contracts to retrieve

        Returns:
            List of sample contracts

        Raises:
            RuntimeError: If not connected
        """
        if not self._logged_in or not self._api:
            raise RuntimeError("Not connected to Shioaji API")

        try:
            # Note: This might fail depending on Shioaji version
            # In newer versions, you might need to fetch contracts first
            contracts = []
            self._log(f"Fetching {limit} sample contracts...")
            # Add your contract fetching logic here
            return contracts
        except Exception as e:
            self._log(f"Failed to get contracts: {e}", level="error")
            return []

    def get_version(self) -> str:
        """Get Shioaji version.

        Returns:
            Shioaji version string
        """
        return sj.__version__

    def _log(self, message: str, level: str = "info") -> None:
        """Log message with timestamp.

        Args:
            message: Log message
            level: Log level (info, warning, error)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{timestamp}] [Shioaji]"

        if level == "error":
            print(f"{prefix} ERROR: {message}")
        elif level == "warning":
            print(f"{prefix} WARNING: {message}")
        else:
            print(f"{prefix} {message}")
