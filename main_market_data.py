"""Market Data Service Entry Point

專門用於期權報價串流的微服務入口點

此服務：
1. 從 Shioaji 訂閱期權報價（價平 ± 8 檔 call）
2. 推播即時行情給 Node.js Socket Hub
3. 具備完整的錯誤處理與自動重連機制
4. 適合在 Docker 環境中運行
"""

import logging
from src.app_factory import create_market_data_app

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Application entry point.

    建立並啟動市場資料服務
    所有組件建立都委託給 factory 模組
    """
    logger.info("=" * 60)
    logger.info("Market Data Service Starting")
    logger.info("=" * 60)

    # 使用 factory 建立應用程式
    # gateway_url 會從 GATEWAY_URL 環境變數讀取（預設：http://localhost:3001）
    # 憑證會從 SJ_KEY, SJ_SEC, CA_CERT_PATH, CA_PASSWORD 環境變數讀取
    service = create_market_data_app(
        simulation=True,  # 模擬模式
        heartbeat_interval=10,  # 心跳間隔 10 秒
        snapshot_interval=5,  # 快照輪詢間隔 5 秒
        contract_update_interval=1  # 合約更新檢查間隔 1 秒
    )

    try:
        service.start()
    except KeyboardInterrupt:
        logger.info("收到鍵盤中斷信號")
    except SystemExit:
        # 環境變數驗證失敗，讓程式正常退出
        pass
    except Exception as e:
        logger.error(f"致命錯誤: {e}", exc_info=True)
    finally:
        # 確保即使發生未預期的錯誤也能清理資源
        if service.is_running():
            service.stop()

    logger.info("=" * 60)
    logger.info("Market Data Service Stopped")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
