# Dogbro Index API

台灣金融市場期權報價串流微服務系統，基於 Shioaji API 提供即時市場資料推播功能。

## 系統架構

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Applications                       │
│                    (Browser / Mobile / Desktop)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ WebSocket (Socket.IO)
                             │
                ┌────────────▼────────────┐
                │   Socket Hub Service    │
                │    (Node.js Gateway)    │
                │      Port: 3001         │
                └────────────┬────────────┘
                             │ Socket.IO Client Connection
                             │
            ┌────────────────▼────────────────┐
            │  Market Data Service (Python)   │
            │                                 │
            │  ┌───────────────────────────┐  │
            │  │  MarketDataService        │  │
            │  │  - Contract Manager       │  │
            │  │  - Quote Subscription     │  │
            │  │  - Snapshot Polling       │  │
            │  │  - Heartbeat Monitor      │  │
            │  └───────────┬───────────────┘  │
            │              │                   │
            │  ┌───────────▼───────────────┐  │
            │  │   ShioajiClient           │  │
            │  │   - API Authentication    │  │
            │  │   - Quote Streaming       │  │
            │  │   - Connection Retry      │  │
            │  └───────────┬───────────────┘  │
            └──────────────┼───────────────────┘
                           │ Shioaji API
                           │
              ┌────────────▼────────────┐
              │   Shioaji API Server    │
              │  (台灣證券交易所)        │
              │  - 期權即時報價         │
              │  - 價平合約追蹤         │
              └─────────────────────────┘
```

## 專案結構

```
dogbro-index-api/
├── main.py                      # 微服務入口點
├── docker-compose.yml           # Docker Compose 編排
├── Dockerfile                   # Python 服務容器化配置
├── requirements.txt             # Python 依賴
├── pyproject.toml               # 專案設定
├── pytest.ini                   # 測試設定
│
├── gateway/                     # Node.js Socket Hub
│   ├── server.js                # WebSocket 中繼伺服器
│   ├── Dockerfile               # Node.js 服務容器化配置
│   └── package.json             # Node.js 依賴
│
├── src/
│   ├── services/                # 服務層
│   │   ├── market_data_service.py   # 市場資料串流服務
│   │   └── trading_service.py       # 交易服務 (legacy)
│   │
│   ├── trading/                 # Shioaji 整合層
│   │   ├── shioaji_client.py        # Shioaji API 客戶端
│   │   ├── contract_manager.py      # 合約管理器
│   │   └── market_data_handler.py   # 市場資料處理器
│   │
│   ├── gateway/                 # Socket.IO 客戶端
│   │   └── gateway_client.py        # 與 Socket Hub 通訊
│   │
│   ├── sj_trading/              # 交易計算工具
│   │   └── xq_ivolatility.py        # 隱含波動率計算器
│   │
│   ├── utils/                   # 工具模組
│   │   └── config.py                # 環境變數配置管理
│   │
│   └── app_factory.py           # 應用程式工廠模式
│
└── tests/                       # 測試套件
    ├── test_market_data_service.py
    ├── test_shioaji_client.py
    ├── test_contract_manager.py
    └── test_gateway_client.py
```

## 核心功能

### 微服務架構
- **Socket Hub (Node.js)**: WebSocket 事件中繼伺服器，提供即時雙向通訊
- **Market Data Service (Python)**: 期權報價串流微服務，處理 Shioaji API 整合
- **Docker Compose 編排**: 容器化部署，服務自動啟動與健康檢查

### 市場資料服務
- **即時報價訂閱**: 自動訂閱價平附近 ± 8 檔 Call 期權報價
- **動態合約追蹤**: 每秒檢查並更新價平合約，自動調整訂閱清單
- **快照輪詢**: 定期輪詢合約快照，確保資料完整性
- **心跳監控**: 定期發送心跳訊號，確保連線健康
- **自動重連機制**: 斷線自動重連，保證服務穩定性

### Shioaji 整合
- **憑證管理**: 安全的 API 金鑰和 CA 憑證管理
- **模擬模式**: 支援模擬環境測試
- **錯誤處理**: 完整的異常處理與錯誤日誌
- **連線池管理**: 高效的 API 連線管理

### 技術特性
- **Factory Pattern**: 應用程式工廠模式，依賴注入
- **Type Safety**: 完整的型別提示與驗證
- **Logging**: 結構化日誌輸出
- **Testing**: 完整的單元測試覆蓋率 (90%+)
- **隱含波動率計算器**: XQ 風格的 Black-Scholes IV 計算器

## 快速開始

### 前置需求

- Docker & Docker Compose
- Shioaji API 憑證 (API key, secret key, CA certificate)

### 安裝步驟

1. Clone 專案：
```bash
git clone https://github.com/julian7862/dogbro-index-api.git
cd dogbro-index-api
```

2. 配置環境變數：
```bash
cp .env.example .env
# 編輯 .env 填入你的 Shioaji 憑證
```

必要的環境變數：
- `SJ_KEY`: Shioaji API key
- `SJ_SEC`: Shioaji secret key
- `CA_CERT_PATH`: CA 憑證路徑 (.pfx 檔案)
- `CA_PASSWORD`: CA 憑證密碼

3. 啟動服務：
```bash
docker-compose up -d
```

4. 檢查服務狀態：
```bash
docker-compose ps
docker-compose logs -f
```

### 本地開發模式

如果你想在本地開發而不使用 Docker：

1. 安裝 Python 依賴：
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. 啟動 Socket Hub：
```bash
cd gateway
npm install
npm start
```

3. 啟動 Market Data Service：
```bash
python main.py
```

## 服務配置

### 環境變數

**Shioaji 憑證** (必要):
- `SJ_KEY`: Shioaji API 金鑰
- `SJ_SEC`: Shioaji 密鑰
- `CA_CERT_PATH`: CA 憑證檔案路徑 (.pfx)
- `CA_PASSWORD`: CA 憑證密碼

**服務設定** (選填):
- `GATEWAY_URL`: Socket Hub URL (預設: `http://localhost:3001`)
- `PYTHONUNBUFFERED`: Python 輸出緩衝 (預設: `1`)
- `TZ`: 時區設定 (預設: `Asia/Taipei`)

### Docker Compose 服務

系統包含兩個服務：

1. **socket-hub**: Node.js WebSocket 中繼伺服器
   - Port: 3001
   - 健康檢查: `/healthz`
   - 自動重啟: `unless-stopped`

2. **python-market-data**: Python 市場資料服務
   - 依賴: socket-hub (等待健康檢查通過)
   - 自動重啟: `always`
   - 連接到 Shioaji API

## 使用方式

### 連接到 WebSocket

客戶端可透過 Socket.IO 連接到 `http://localhost:3001`：

```javascript
import io from 'socket.io-client';

const socket = io('http://localhost:3001');

// 接收即時報價
socket.on('quote_update', (data) => {
  console.log('Quote:', data);
});

// 接收心跳
socket.on('heartbeat', (data) => {
  console.log('Heartbeat:', data);
});

// 接收合約更新
socket.on('contracts_loaded', (data) => {
  console.log('Contracts:', data);
});
```

### 使用隱含波動率計算器

```python
from src.sj_trading.xq_ivolatility import XQIVolatility

# 計算隱含波動率
iv = XQIVolatility.ivolatility(
    call_put_flag="C",      # "C" = Call, "P" = Put
    spot_price=18000,       # 現貨價格
    strike_price=18500,     # 履約價
    d_to_m=30,              # 到期天數
    rate_100=2.0,           # 無風險利率 (%)
    b_100=2.0,              # 持有成本 (%)
    option_price=150        # 選擇權市價
)
print(f"隱含波動率: {iv}%")
```

### 常用指令

```bash
# 啟動所有服務
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 查看特定服務日誌
docker-compose logs -f python-market-data

# 重啟服務
docker-compose restart python-market-data

# 停止所有服務
docker-compose down

# 重建並啟動
docker-compose up -d --build
```

## 架構設計原則

### 微服務分離
- **Socket Hub**: 純粹的事件中繼，不包含業務邏輯
- **Market Data Service**: 專注於市場資料獲取與處理
- **鬆耦合**: 服務間透過 Socket.IO 通訊，可獨立部署與擴展

### 依賴注入 & Factory Pattern
- **AppFactory** (`src/app_factory.py`): 集中管理組件建立
- **GatewayClient**: Socket.IO 客戶端抽象
- **ShioajiClient**: Shioaji API 客戶端封裝
- **MarketDataService**: 服務編排與生命週期管理

### 配置管理 (`src/utils/config.py`)
- **Immutable**: 使用 frozen dataclass 防止意外修改
- **Fail-fast**: 啟動時驗證所有必要環境變數
- **Type-safe**: 完整的型別提示
- **Single source of truth**: 全域配置單例

### 錯誤處理與重試
- **自動重連**: Gateway 斷線自動重連
- **優雅關閉**: 信號處理與資源清理
- **結構化日誌**: 使用 Python logging 模組
- **健康檢查**: Docker healthcheck 整合

## 開發指南

### 專案結構說明

- `main.py`: 微服務入口點
- `src/services/`: 服務層，編排業務流程
- `src/trading/`: Shioaji API 整合與合約管理
- `src/gateway/`: Socket.IO 客戶端通訊
- `src/sj_trading/`: 金融計算工具 (IV, Greeks)
- `src/utils/`: 共用工具模組
- `tests/`: 完整的測試套件

### 測試

執行測試：

```bash
# 執行所有測試
pytest

# 查看覆蓋率報告
pytest --cov=src --cov-report=html

# 執行特定測試
pytest tests/test_market_data_service.py -v
```

### 程式碼風格

- 遵循 PEP 8 規範
- 使用型別提示 (Type Hints)
- Dataclass 用於資料結構
- 記錄複雜的演算法與業務邏輯
- Docstring 使用 Google 風格

## 監控與除錯

### 健康檢查

檢查 Socket Hub 健康狀態：
```bash
curl http://localhost:3001/healthz
```

預期回應：
```json
{"status": "ok"}
```

### 查看日誌

```bash
# 即時查看所有服務日誌
docker-compose logs -f

# 只看 Python 服務
docker-compose logs -f python-market-data

# 只看 Socket Hub
docker-compose logs -f socket-hub

# 查看最近 100 行
docker-compose logs --tail=100 python-market-data
```

### 常見問題排除

**1. Python 服務無法連接到 Shioaji**
- 檢查 `.env` 憑證是否正確
- 確認 CA 憑證檔案路徑正確
- 查看日誌確認錯誤訊息：`docker-compose logs python-market-data`

**2. Socket Hub 連線失敗**
- 確認 port 3001 沒有被佔用：`lsof -i :3001`
- 檢查防火牆設定
- 確認 Docker 網路正常：`docker network ls`

**3. 報價資料沒有更新**
- 檢查是否在交易時間內
- 確認合約訂閱狀態：查看日誌中的 "contracts_loaded" 事件
- 重啟 Python 服務：`docker-compose restart python-market-data`

**4. 服務頻繁重啟**
- 查看錯誤日誌：`docker-compose logs --tail=200 python-market-data`
- 檢查記憶體使用：`docker stats`
- 驗證環境變數設定

### 效能監控

查看容器資源使用：
```bash
docker stats
```

查看服務狀態：
```bash
docker-compose ps
```

## 相關文件

- [Market Data Service 詳細說明](MARKET_DATA_SERVICE.md)
- [Docker 部署指南](DOCKER.md)
- [測試結果報告](TEST_RESULTS.md)

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
