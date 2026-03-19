# Market Data Service 使用指南

## 概述

Market Data Service 是一個專門用於期權報價串流的微服務，負責：

1. **從 Shioaji 訂閱期權報價**：動態追蹤價平 ± 8 檔買權 (Call)
2. **推播即時行情**：透過 Socket.IO 推送給 Node.js Hub
3. **穩定性保證**：完整的錯誤處理與自動重連機制
4. **Docker 支援**：適合在容器環境中運行

## 架構特點

### 1. 環境變數驅動 ✅
- 從環境變數讀取所有憑證（不依賴外部檔案）
- 啟動前驗證憑證完整性
- 憑證缺失時自動終止（觸發 Docker 重啟）

### 2. 強化的 Socket.IO 重連機制 ✅
- 自動重連（無限重試）
- 初始延遲 1 秒，最大延遲 10 秒
- 隨機因子避免同時重連
- 清晰的連線/斷線日誌

### 3. 模組化動態合約追蹤 ✅
- 自動計算價平履約價 (ATM)
- 動態訂閱價平 ± 8 檔買權
- 安全處理合約查找（避免 KeyError/IndexError）
- 價格無效時暫停訂閱更新

### 4. 行情狀態維護與非同步推播 ✅
- Tick/BidAsk 回呼包含完整錯誤處理
- Socket 斷線時不會 crash
- 快照輪詢執行緒具備 try-except 保護
- 單次失敗不影響後續輪詢

### 5. 自動排程重啟機制 (Crash-Only Design) ✅
- 採用 **Crash-Only Software** 設計理念
- 在特定時間點自動優雅關閉並由 Docker 重新啟動
- 避免日夜盤轉換與清晨洗帳造成的髒狀態問題

#### 排程重啟時間點

服務會在每天以下時間點自動重啟：

| 時間  | 目的 | 原因 |
|------|------|------|
| **06:30** | 清晨洗帳後重啟 | 券商系統維護完成，清除舊合約狀態 |
| **08:40** | 日盤開盤前重啟 | 重新抓取最新 T 字報價表，確保日盤乾淨啟動 |
| **14:55** | 夜盤開盤前重啟 | 清除日盤狀態，準備夜盤交易 |

#### 運作機制

1. **時間檢測**：服務在主迴圈中每秒檢查當前時間
2. **優雅關閉**：符合重啟時間時，服務會：
   - 登出 Shioaji 連線
   - 斷開 Gateway Socket.IO 連線
   - 清理所有資源
3. **進程終止**：呼叫 `sys.exit(0)` 終止 Python 進程
4. **Docker 重啟**：由於 `docker-compose.yml` 設定了 `restart: always`，Docker 會自動重新啟動容器
5. **重複防護**：使用 `_last_restart_minute` 變數避免同一分鐘內重複觸發

#### 日誌範例

重啟觸發時會看到：

```
[WARNING] 🔄 [排程] 觸發系統換盤重啟 (時間: 08:40)，準備優雅關閉...
[INFO] 正在停止市場資料服務...
[INFO] 市場資料服務已停止
```

隨後 Docker 會重新啟動服務：

```
[INFO] Market Data Service Starting
[INFO] 環境變數驗證通過
...
```

#### 優點

- **狀態清理**：完全清除記憶體中的舊合約、訂閱狀態
- **合約更新**：重新從期交所抓取最新的合約資料
- **防止髒狀態**：避免日盤/夜盤切換時的資料不一致
- **簡單可靠**：不需要複雜的狀態管理邏輯
- **易於測試**：透過 Mock 時間即可測試重啟邏輯

#### 注意事項

- 重啟過程約需 10-30 秒（取決於 Shioaji 登入速度）
- 重啟期間會短暫中斷行情推播
- 確保 `docker-compose.yml` 有設定 `restart: always`
- 可透過環境變數或修改程式碼調整重啟時間點

## 環境變數設定

### 必要環境變數

```bash
# Shioaji API 憑證
SJ_KEY=your_api_key_here          # 或使用 API_KEY（向後相容）
SJ_SEC=your_secret_key_here       # 或使用 SECRET_KEY（向後相容）
CA_CERT_PATH=/path/to/cert.pfx    # CA 憑證路徑
CA_PASSWORD=your_ca_password       # CA 憑證密碼

# Socket Hub URL
GATEWAY_URL=http://socket-hub:3001  # Docker 環境
# GATEWAY_URL=http://localhost:3001 # 本地開發
```

### .env 檔案範例

```bash
# Shioaji API
SJ_KEY=YOUR_API_KEY_HERE
SJ_SEC=YOUR_SECRET_KEY_HERE
CA_CERT_PATH=/app/certs/your_cert.pfx
CA_PASSWORD=YOUR_CERT_PASSWORD

# Gateway
GATEWAY_URL=http://socket-hub:3001

# 時區
TZ=Asia/Taipei

# Python
PYTHONUNBUFFERED=1
```

## 使用方式

### 方式 1：直接執行 Python

```bash
# 設定環境變數
export SJ_KEY="your_key"
export SJ_SEC="your_secret"
export CA_CERT_PATH="/path/to/cert.pfx"
export CA_PASSWORD="your_password"
export GATEWAY_URL="http://localhost:3001"

# 執行
python main_market_data.py
```

### 方式 2：使用 Docker Compose（推薦）

```bash
# 啟動所有服務
docker-compose up -d

# 查看市場資料服務日誌
docker-compose logs -f python-market-data

# 重啟服務
docker-compose restart python-market-data

# 停止服務
docker-compose down
```

## 程式碼結構

```
src/
├── services/
│   └── market_data_service.py    # 主服務（協調器）
├── trading/
│   ├── contract_manager.py       # 合約管理器
│   ├── market_data_handler.py    # 行情處理器
│   └── shioaji_client.py         # Shioaji 客戶端（已強化）
└── gateway/
    └── gateway_client.py          # Gateway 客戶端（已強化重連）

tests/
├── test_market_data_service.py   # 服務單元測試
├── test_contract_manager.py      # 合約管理器測試
└── test_market_data_handler.py   # 行情處理器測試
```

## 測試

### 執行所有測試

```bash
# 安裝測試依賴
pip install -r requirements.txt

# 執行測試
pytest

# 產生覆蓋率報告
pytest --cov=src --cov-report=html
```

### 執行特定測試

```bash
# 只測試市場資料服務
pytest tests/test_market_data_service.py

# 只測試合約管理器
pytest tests/test_contract_manager.py

# 只測試行情處理器
pytest tests/test_market_data_handler.py

# 執行特定測試函數
pytest tests/test_market_data_service.py::TestMarketDataService::test_validate_environment_success
```

## 錯誤處理機制

### 1. 環境變數驗證失敗

**現象**：
```
[ERROR] 缺少必要的環境變數：
  - SJ_KEY (Shioaji API Key)
程式即將終止，等待 Docker 重啟...
```

**解決方案**：
1. 檢查 `.env` 檔案是否正確設定
2. 確認 Docker Compose 的 `env_file` 設定
3. 查看環境變數是否正確傳遞：`docker-compose exec python-market-data env | grep SJ_`

### 2. Shioaji 登入失敗

**現象**：
```
[ERROR] 登入失敗: Invalid API Key
請檢查 API Key 和 Secret Key 是否正確
```

**解決方案**：
1. 確認 API Key 和 Secret Key 正確
2. 檢查 API Key 是否已啟用
3. 確認帳號是否有期權交易權限

### 3. CA 憑證啟用失敗

**現象**：
```
[ERROR] CA 憑證啟用失敗: Invalid password
請檢查憑證路徑 (/app/certs/cert.pfx) 和密碼是否正確
```

**解決方案**：
1. 確認憑證檔案存在
2. 檢查憑證密碼是否正確
3. 確認憑證路徑在 Docker 中可訪問

### 4. Gateway 連線失敗

**現象**：
```
[WARNING] Socket.IO 連線已中斷（將自動重連）
```

**解決方案**：
- 這是正常現象，服務會自動重連
- 如果持續無法連線，檢查：
  1. Gateway 服務是否正常運行：`docker-compose ps`
  2. 網路是否正常：`docker-compose exec python-market-data ping socket-hub`
  3. GATEWAY_URL 環境變數是否正確

### 5. 合約查找失敗

**現象**：
```
[WARNING] 找不到履約價範圍 [17700, 17800, ...] 的合約
```

**解決方案**：
- 可能是交易時段外或合約尚未下載
- 服務會繼續運行，等待合約資料可用

## 日誌說明

### 啟動流程日誌

```
[INFO] Market Data Service Starting
[INFO] 環境變數驗證通過
[INFO] 正在連接到 Gateway: http://socket-hub:3001
[INFO] 已連接到 Gateway: http://socket-hub:3001
[INFO] 正在初始化 Shioaji API...
[INFO] 正在登入 Shioaji...
[INFO] 登入成功
[INFO] 正在啟用 CA 憑證...
[INFO] CA 憑證啟用成功
[INFO] 正在抓取合約資料...
[INFO] 合約資料抓取成功
[INFO] 行情回呼函數設定完成
[INFO] 已發送就緒狀態
[INFO] 快照輪詢執行緒已啟動（間隔 5 秒）
[INFO] 市場資料服務啟動成功
[INFO] 主迴圈已啟動。按 Ctrl+C 退出。
```

### 運行中日誌

```
[INFO] 合約訂閱更新完成 | ATM: 18000 | 訂閱: 17 個合約
[DEBUG] 已訂閱合約: TXO18000C
[DEBUG] 已訂閱合約: TXO18100C
...
```

### 行情資料日誌

```
[INFO] Emitted event: market_tick
[INFO] Emitted event: market_bidask
[INFO] Emitted event: market_snapshot
```

## 監控指標

### 心跳資料

每 10 秒發送一次心跳，包含：

```json
{
  "status": "running",
  "shioaji_connected": true,
  "gateway_connected": true,
  "current_price": 18000.0,
  "subscribed_contracts": 17
}
```

### 推播事件

- `market_tick`: Tick 資料（即時成交）
- `market_bidask`: 委買委賣資料
- `market_snapshot`: 快照資料（每 5 秒）
- `heartbeat`: 心跳（每 10 秒）
- `python_error`: 錯誤訊息

## 進階設定

### 調整訂閱範圍

修改 `main_market_data.py`：

```python
service = create_market_data_app(
    simulation=True,
    heartbeat_interval=10,      # 心跳間隔
    snapshot_interval=5,        # 快照間隔
    contract_update_interval=1  # 合約更新間隔
)
```

修改合約範圍（在 `market_data_service.py`）：

```python
self._contract_manager.update_subscriptions(
    current_price=current_price,
    range_strikes=8,    # 改為 10 檔
    option_type='call'  # 改為 'put' 或同時訂閱兩者
)
```

### 效能調校

1. **減少快照頻率**：調高 `snapshot_interval`（例如 10 秒）
2. **減少合約數量**：調低 `range_strikes`（例如 5 檔）
3. **增加心跳間隔**：調高 `heartbeat_interval`（例如 30 秒）

## 故障排除

### 問題：服務不斷重啟

```bash
# 查看服務狀態
docker-compose ps

# 查看完整日誌
docker-compose logs python-market-data

# 可能原因：
# 1. 環境變數缺失
# 2. 憑證無效
# 3. Shioaji API 問題
```

### 問題：無法收到行情資料

```bash
# 檢查訂閱狀態（查看日誌）
docker-compose logs python-market-data | grep "訂閱"

# 可能原因：
# 1. 交易時段外
# 2. 合約資料未下載完成
# 3. 沒有有效的當前價格
```

### 問題：記憶體使用過高

```bash
# 查看容器資源使用
docker stats python-market-data

# 解決方案：
# 1. 減少訂閱的合約數量
# 2. 增加快照間隔
# 3. 在 docker-compose.yml 中設定記憶體限制
```

## 生產環境建議

1. **設定資源限制**（在 docker-compose.yml）：
```yaml
services:
  python-market-data:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
```

2. **日誌管理**：
```yaml
services:
  python-market-data:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

3. **健康檢查**：監控心跳事件，超過 30 秒無心跳則告警

4. **備份機制**：準備備用服務實例，主服務失敗時自動切換

## 技術支援

如有問題，請檢查：
1. GitHub Issues
2. Docker 日誌：`docker-compose logs python-market-data`
3. Shioaji 官方文件
