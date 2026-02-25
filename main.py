"""Trading application entry point.

This module serves as a clean entry point, delegating responsibilities
to specialized services following SOLID principles.
"""

from src.utils.config import config
from src.gateway.gateway_client import GatewayClient, GatewayConfig
from src.trading.shioaji_client import ShioajiClient, ShioajiConfig
from src.services.trading_service import TradingService


def create_gateway_client() -> GatewayClient:
    """Factory function to create Gateway client.

    Returns:
        Configured GatewayClient instance
    """
    gateway_config = GatewayConfig(
        url='http://localhost:3001',
        reconnection=True
    )
    return GatewayClient(gateway_config)


def create_shioaji_client() -> ShioajiClient:
    """Factory function to create Shioaji client.

    Returns:
        Configured ShioajiClient instance
    """
    shioaji_config = ShioajiConfig(
        api_key=config.api_key,
        secret_key=config.secret_key,
        ca_cert_path=config.ca_cert_path,
        ca_password=config.ca_password,
        simulation=True
    )
    return ShioajiClient(shioaji_config)


def create_trading_service() -> TradingService:
    """Factory function to create Trading service.

    Returns:
        Configured TradingService instance
    """
    gateway_client = create_gateway_client()
    shioaji_client = create_shioaji_client()

    return TradingService(
        gateway_client=gateway_client,
        shioaji_client=shioaji_client,
        heartbeat_interval=10
    )


def main() -> None:
    """Application entry point.

    Creates and starts the trading service with proper error handling.
    """
    print("=" * 60)
    print("Trading Application Starting")
    print("=" * 60)

    service = create_trading_service()

    try:
        service.start()
    except Exception as e:
        print(f"\nFatal error: {e}")
        return
    finally:
        # Ensure cleanup even on unexpected errors
        if service.is_running():
            service.stop()

    print("\n" + "=" * 60)
    print("Trading Application Stopped")
    print("=" * 60)


if __name__ == "__main__":
    main()
