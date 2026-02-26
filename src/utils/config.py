import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""
    api_key: str
    secret_key: str
    ca_cert_path: str
    ca_password: str

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables.

        支援多種環境變數名稱（向後相容）：
        - SJ_KEY 或 API_KEY
        - SJ_SEC 或 SECRET_KEY
        - CA_CERT_PATH
        - CA_PASSWORD

        Raises:
            ValueError: If any required environment variable is missing.
        """
        # 支援新舊環境變數名稱
        config_values = {}

        # API Key - 優先使用 SJ_KEY，其次使用 API_KEY
        api_key = os.getenv("SJ_KEY") or os.getenv("API_KEY")
        if not api_key:
            raise ValueError("Missing API Key: Please set SJ_KEY or API_KEY environment variable")
        config_values["api_key"] = api_key

        # Secret Key - 優先使用 SJ_SEC，其次使用 SECRET_KEY
        secret_key = os.getenv("SJ_SEC") or os.getenv("SECRET_KEY")
        if not secret_key:
            raise ValueError("Missing Secret Key: Please set SJ_SEC or SECRET_KEY environment variable")
        config_values["secret_key"] = secret_key

        # CA 憑證路徑
        ca_cert_path = os.getenv("CA_CERT_PATH")
        if not ca_cert_path:
            raise ValueError("Missing CA Cert Path: Please set CA_CERT_PATH environment variable")
        config_values["ca_cert_path"] = ca_cert_path

        # CA 憑證密碼
        ca_password = os.getenv("CA_PASSWORD")
        if not ca_password:
            raise ValueError("Missing CA Password: Please set CA_PASSWORD environment variable")
        config_values["ca_password"] = ca_password

        return cls(**config_values)


# Global config instance
config = Config.from_env()
