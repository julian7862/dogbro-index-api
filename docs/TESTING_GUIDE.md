# Integration Testing Guide

## Quick Start - Manual Testing

### Terminal 1: Gateway Server
```bash
cd gateway
node server.js
```
Expected output:
```
============================================================
[WebSocket Hub] 運行於 http://0.0.0.0:3001
[WebSocket Hub] Socket.IO 中繼已啟用
============================================================
```

### Terminal 2: Python Market Data Service
```bash
# In dogbro-index-api directory
python -m src.main
```
Expected output:
```
[2026-03-04 17:00:00] [market_data_service] INFO: 正在啟動市場資料服務...
[2026-03-04 17:00:00] [gateway_client] INFO: 正在連接到 Gateway: http://localhost:3001
[2026-03-04 17:00:00] [gateway_client] INFO: Socket.IO 連線已建立
[2026-03-04 17:00:00] [market_data_service] INFO: 市場資料服務啟動成功
```

### Terminal 3: React Frontend
```bash
cd ../dogbro-index-client
npm start
```
Browser should open at: http://localhost:3000

## Automated Testing Script

### Option 1: All-in-One Launch
```bash
./test-integration.sh
```

This will:
1. Check dependencies
2. Start Gateway Server (port 3001)
3. Start Python Backend
4. Start React Frontend (port 3000)
5. Open browser automatically

Press `Ctrl+C` to stop all services.

## Verification Checklist

### 1. Gateway Connection
In Terminal 1 (Gateway), you should see:
```
[Socket] 客戶端已連線：<socket-id>
[中繼] shioaji_ready: [{ status: 'ready', ... }]
[中繼] heartbeat: [{ status: 'running', ... }]
```

### 2. Frontend Status Indicators
In browser (http://localhost:3000), check:
- [ ] Socket: Connected (green)
- [ ] Service: Ready (green)
- [ ] Heartbeat section shows data
- [ ] Current price is updating
- [ ] Subscribed contracts count > 0

### 3. Real-time Data Flow
You should see:
- [ ] TickCard components with live OHLC prices
- [ ] OrderBookCard with bid/ask data
- [ ] SnapshotCard with contract details
- [ ] Timestamps updating in real-time

## Troubleshooting

### Frontend shows "Disconnected"
1. Check Gateway is running on port 3001:
   ```bash
   lsof -i :3001
   ```
2. Check `.env` in frontend:
   ```
   REACT_APP_GATEWAY_URL=http://localhost:3001
   ```

### No market data appearing
1. Check Python service is connected:
   - Look for "Socket.IO 連線已建立" in Terminal 2
2. Check Shioaji credentials in `.env`:
   ```
   SJ_KEY=your_api_key
   SJ_SEC=your_secret_key
   ```

### Gateway relay not working
Check Gateway logs for:
```
[中繼] market_tick: ...
[中繼] market_bidask: ...
[中繼] market_snapshot: ...
```

If missing, Python service may not be emitting events.

## Event Flow Diagram

```
Shioaji API
    ↓
Python Market Data Service
    ↓ (emit via socketio-client)
Gateway Server (Port 3001)
    ↓ (broadcast to all clients)
React Frontend (Port 3000)
    ↓
Browser Display
```

## Expected Events

The Python backend should emit these events to Gateway:

1. **shioaji_ready** (once on startup)
   - Indicates service is ready
   - Contains: status, simulation, version, service_type

2. **heartbeat** (every 10 seconds)
   - Service health status
   - Contains: status, connections, current_price, subscribed_contracts

3. **market_tick** (real-time)
   - OHLC price data
   - Contains: exchange, code, datetime, open, high, low, close, price, volume

4. **market_bidask** (real-time)
   - Order book data
   - Contains: exchange, code, bid_price, bid_volume, ask_price, ask_volume

5. **market_snapshot** (every 5 seconds)
   - Market summary
   - Contains: code, name, open, high, low, close, volume, amount

6. **python_error** (on errors)
   - Error reporting
   - Contains: error, service

## Port Reference

| Service | Port | Protocol |
|---------|------|----------|
| React Frontend | 3000 | HTTP |
| Gateway Server | 3001 | Socket.IO |
| Python Backend | N/A | Socket.IO Client |

## Success Criteria

✅ All three terminals show no errors
✅ Frontend status indicators are green
✅ Live market data is updating
✅ Console shows no connection errors
✅ Data cards show real prices (not placeholders)
