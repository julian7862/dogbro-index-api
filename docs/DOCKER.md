# Docker 部署指南

本專案使用 Docker Compose 將系統拆分為兩個獨立的容器化服務。

## 架構概覽

```
┌─────────────────┐
│  React 前端     │ (獨立部署)
│  Port: 3000     │
└────────┬────────┘
         │ WebSocket
         ↓
┌─────────────────┐
│  Socket Hub     │ (Node.js)
│  Port: 3001     │ ← 純粹的事件中繼
└────────┬────────┘
         │ WebSocket
         ↓
┌─────────────────┐
│ Python Crawler  │ (Shioaji)
│ (背景服務)       │ ← 報價資料串流
└─────────────────┘
```

## 服務說明

### 1. socket-hub (Node.js)
- **用途**: 純粹的 WebSocket 事件中繼站
- **功能**:
  - 接收所有 Socket.IO 事件
  - 廣播給所有連線的客戶端
  - 不處理業務邏輯
- **端口**: 3001
- **健康檢查**: `GET /healthz`

### 2. python-crawler (Python)
- **用途**: Shioaji 報價資料串流服務
- **功能**:
  - 連線到 Shioaji API
  - 訂閱市場報價
  - 發送資料到 Socket Hub
- **依賴**: socket-hub (必須先啟動)
- **重啟策略**: always (崩潰自動重啟)

## 快速開始

### 前置需求

1. 安裝 Docker 和 Docker Compose
2. 準備 `.env` 檔案（參考 `.env.example`）

### 設定環境變數

在專案根目錄建立 `.env` 檔案：

```bash
# Shioaji API 憑證
API_KEY=your_api_key_here
SECRET_KEY=your_secret_key_here
CA_CERT_PATH=/path/to/cert.pfx
CA_PASSWORD=your_ca_password
```

### 啟動服務

```bash
# 建構並啟動所有服務
docker-compose up -d

# 查看服務狀態
docker-compose ps

# 查看日誌
docker-compose logs -f

# 查看特定服務日誌
docker-compose logs -f python-crawler
docker-compose logs -f socket-hub
```

### 停止服務

```bash
# 停止所有服務
docker-compose down

# 停止並刪除 volumes
docker-compose down -v
```

## 開發模式

### 重新建構

```bash
# 重新建構所有服務
docker-compose build

# 重新建構特定服務
docker-compose build python-crawler
docker-compose build socket-hub

# 強制重新建構（不使用快取）
docker-compose build --no-cache
```

### 重啟服務

```bash
# 重啟所有服務
docker-compose restart

# 重啟特定服務
docker-compose restart python-crawler
```

### 進入容器

```bash
# 進入 Python 容器
docker-compose exec python-crawler sh

# 進入 Socket Hub 容器
docker-compose exec socket-hub sh
```

## 監控與除錯

### 健康檢查

```bash
# 檢查 Socket Hub 狀態
curl http://localhost:3001/healthz

# 查看容器健康狀態
docker-compose ps
```

### 查看日誌

```bash
# 即時查看所有日誌
docker-compose logs -f

# 查看最近 100 行日誌
docker-compose logs --tail=100

# 查看特定時間範圍
docker-compose logs --since 30m
```

### 常見問題

#### Python 服務連線失敗

**現象**: Python 無法連線到 Socket Hub

**解決方案**:
1. 確認 Socket Hub 已啟動：`docker-compose ps`
2. 檢查網路連線：`docker-compose exec python-crawler ping socket-hub`
3. 查看日誌：`docker-compose logs socket-hub`

#### 憑證問題

**現象**: Shioaji 登入失敗

**解決方案**:
1. 確認 `.env` 檔案設定正確
2. 檢查 CA 憑證路徑
3. 如需掛載憑證，修改 `docker-compose.yml` 中的 volumes 設定

#### 服務不斷重啟

**現象**: `docker-compose ps` 顯示服務持續重啟

**解決方案**:
1. 查看錯誤日誌：`docker-compose logs python-crawler`
2. 檢查環境變數設定
3. 確認依賴服務正常運行

## 生產環境部署

### 環境變數最佳實踐

```bash
# 不要將 .env 檔案提交到 Git
echo ".env" >> .gitignore

# 在伺服器上設定環境變數
export API_KEY="..."
export SECRET_KEY="..."
export CA_CERT_PATH="..."
export CA_PASSWORD="..."
```

### 資源限制

在 `docker-compose.yml` 中添加資源限制：

```yaml
services:
  python-crawler:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
        reservations:
          memory: 256M
```

### 日誌管理

```yaml
services:
  python-crawler:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 架構優勢

1. **關注點分離**: WebSocket Hub 只負責中繼，業務邏輯在 Python 服務
2. **獨立擴展**: 可以獨立擴展 Socket Hub 或 Python 服務
3. **容錯性**: Python 崩潰時自動重啟，不影響 Socket Hub
4. **開發效率**: 可以獨立開發和測試各個服務
5. **部署靈活**: 可以部署到任何支援 Docker 的環境

## 下一步

- [ ] 前端應用連線到 `ws://localhost:3001`
- [ ] 設定 CI/CD 自動建構 Docker 映像檔
- [ ] 部署到雲端平台 (AWS ECS, Google Cloud Run, etc.)
- [ ] 設定監控和告警系統
- [ ] 實作資料持久化（如需要）
