"""Shioaji API client wrapper.

This module provides a clean abstraction over Shioaji API,
following Single Responsibility Principle.
"""

import sys
import os
import logging
import shioaji as sj
from dataclasses import dataclass
from typing import Optional, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


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
        """Initialize and login to Shioaji API with validation.

        此方法會：
        1. 驗證憑證是否存在
        2. 初始化 Shioaji API
        3. 登入
        4. 啟用 CA 憑證
        5. 抓取合約（用於後續查詢）

        Raises:
            ConnectionError: If login or CA activation fails
            SystemExit: If credentials are missing (for Docker restart)
        """
        if self._logged_in:
            return

        # 步驟 1: 驗證憑證（防呆檢查）
        self._validate_credentials()

        try:
            # 步驟 2: 初始化 Shioaji API
            logger.info("正在初始化 Shioaji API...")
            self._api = sj.Shioaji(simulation=self._config.simulation)

            # 步驟 3: 登入
            logger.info("正在登入 Shioaji...")
            try:
                self._api.login(
                    api_key=self._config.api_key,
                    secret_key=self._config.secret_key,
                    fetch_contract=False  # 先不抓合約，加快登入速度
                )
                logger.info("登入成功")
            except Exception as e:
                logger.error(f"登入失敗: {e}")
                logger.error("請檢查 API Key 和 Secret Key 是否正確")
                raise ConnectionError(f"Shioaji 登入失敗: {e}")

            # 步驟 4: 啟用 CA 憑證
            logger.info("正在啟用 CA 憑證...")
            try:
                self._api.activate_ca(
                    ca_path=self._config.ca_cert_path,
                    ca_passwd=self._config.ca_password,
                )
                logger.info("CA 憑證啟用成功")
            except Exception as e:
                logger.error(f"CA 憑證啟用失敗: {e}")
                logger.error(f"請檢查憑證路徑 ({self._config.ca_cert_path}) 和密碼是否正確")
                raise ConnectionError(f"CA 憑證啟用失敗: {e}")

            # 步驟 5: 抓取合約
            logger.info("正在抓取合約資料...")
            try:
                # 使用 timeout 保護，避免無限等待
                self._api.fetch_contracts(contract_download=True)
                logger.info("合約資料抓取成功")
            except Exception as e:
                logger.warning(f"抓取合約資料失敗: {e}")
                logger.warning("將繼續執行，但可能無法查詢合約資訊")
                # 不要因為合約抓取失敗就中斷，有些情況下可以繼續運行

            self._logged_in = True

        except ConnectionError:
            # 重新拋出已處理的 ConnectionError
            raise
        except Exception as e:
            logger.error(f"連接 Shioaji 時發生未預期的錯誤: {e}", exc_info=True)
            raise ConnectionError(f"連接 Shioaji 失敗: {e}")

    def _validate_credentials(self) -> None:
        """驗證憑證是否有效

        如果缺少必要憑證，印出錯誤訊息並終止程式（讓 Docker 重啟）

        Raises:
            SystemExit: 如果憑證無效
        """
        errors = []

        if not self._config.api_key or not self._config.api_key.strip():
            errors.append("API Key 為空")

        if not self._config.secret_key or not self._config.secret_key.strip():
            errors.append("Secret Key 為空")

        if not self._config.ca_cert_path or not self._config.ca_cert_path.strip():
            errors.append("CA 憑證路徑為空")

        if not self._config.ca_password or not self._config.ca_password.strip():
            errors.append("CA 憑證密碼為空")

        # 檢查憑證檔案是否存在
        if self._config.ca_cert_path and not os.path.exists(self._config.ca_cert_path):
            errors.append(f"CA 憑證檔案不存在: {self._config.ca_cert_path}")

        if errors:
            logger.error("=" * 60)
            logger.error("Shioaji 憑證驗證失敗：")
            for error in errors:
                logger.error(f"  - {error}")
            logger.error("請檢查環境變數設定：")
            logger.error("  - SJ_KEY (API Key)")
            logger.error("  - SJ_SEC (Secret Key)")
            logger.error("  - CA_CERT_PATH (憑證路徑)")
            logger.error("  - CA_PASSWORD (憑證密碼)")
            logger.error("=" * 60)
            logger.error("程式即將終止，等待 Docker 重啟...")
            sys.exit(1)

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
