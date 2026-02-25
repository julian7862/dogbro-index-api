# Gateway Server - WebSocket Relay

Node.js WebSocket 中繼伺服器，用於管理 Python 進程並提供即時通訊功能。

## 架構說明

```
┌─────────────┐      WebSocket      ┌──────────────┐
│  Browser/   │ <----------------->  │   Gateway    │
│   Client    │                      │  (Node.js)   │
└─────────────┘                      │  Port 3001   │
                                     └──────┬───────┘
                                            │
                                     spawn  │  manages
                                            │
                                     ┌──────▼───────┐
                                     │   Python     │
                                     │   main.py    │
                                     │ (Socket.IO   │
                                     │   Client)    │
                                     └──────────────┘
```

## 功能特性

1. **WebSocket 中繼站**: 使用 Socket.IO 廣播所有事件給連線的客戶端
2. **Python 進程管理**: 自動啟動、重啟和監控 Python 主程式
3. **熱重啟**: 支援動態更新配置並重啟 Python 進程
4. **健康檢查**: 提供 `/health` 端點檢查服務狀態

## API 端點

### GET `/health`
檢查服務狀態

**回應範例:**
```json
{
  "status": "ok",
  "pythonRunning": true,
  "timestamp": "2024-02-25T15:30:00.000Z"
}
```

### POST `/set-sj-key`
設定 Shioaji API 金鑰並重啟 Python 進程

**請求範例:**
```json
{
  "apiKey": "YOUR_API_KEY",
  "secretKey": "YOUR_SECRET_KEY",
  "caCertPath": "/path/to/cert.pfx",
  "caPassword": "YOUR_PASSWORD"
}
```

**回應範例:**
```json
{
  "success": true,
  "message": "Credentials updated and Python process restarted"
}
```

### POST `/restart-python`
手動重啟 Python 進程

**回應範例:**
```json
{
  "success": true,
  "message": "Python process restarted"
}
```

## Socket.IO 事件

### 從 Python 發送的事件

- `python_status`: Python 進程狀態更新
- `shioaji_ready`: Shioaji API 準備就緒
- `contracts_loaded`: 合約資料載入完成
- `heartbeat`: 心跳訊號
- `python_error`: Python 錯誤訊息

### 中繼行為

所有接收到的事件都會自動廣播給其他連線的客戶端。

## 安裝與使用

### 安裝依賴

```bash
cd gateway
npm install
```

### 啟動服務

```bash
npm start
```

### 開發模式

```bash
npm run dev
```

## 環境變數

- `PORT`: 伺服器端口 (預設: 3001)

## 日誌輸出

伺服器會輸出以下類型的日誌：

- `[Gateway]`: Gateway 伺服器事件
- `[Socket]`: WebSocket 連線事件
- `[Relay]`: 事件中繼記錄
- `[Python]`: Python 進程輸出
- `[Python stdout]`: Python 標準輸出
- `[Python stderr]`: Python 錯誤輸出
- `[Config]`: 配置更新事件

## 故障排除

### Python 進程無法啟動

檢查：
1. Python 是否安裝且在 PATH 中
2. `../main.py` 檔案是否存在
3. Python 依賴是否已安裝

### WebSocket 連線失敗

檢查：
1. 防火牆設定
2. Port 3001 是否被佔用
3. CORS 設定是否正確

### 熱重啟失敗

伺服器會自動 kill 舊的 Python 進程再啟動新的。如果重啟失敗，檢查：
1. Python 進程是否正常終止
2. 檔案權限是否正確
3. 環境變數是否正確設定
