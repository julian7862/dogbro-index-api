# Frontend API Documentation - DogBro Market Data

This document describes the frontend application and the Socket.IO API it expects from the backend service.

---

## Frontend Overview

**Repository:** https://github.com/julian7862/dogbro-index-client
**Technology:** React.js with Socket.IO Client
**Port:** 3000
**Backend Expected:** Socket.IO server on port 3001

## Frontend Project Structure

```
dogbro-index-client/
├── public/
│   └── index.html              # HTML template
├── src/
│   ├── services/
│   │   └── socketService.js    # Socket.IO connection manager
│   ├── hooks/
│   │   └── useMarketData.js    # React hook for market data
│   ├── App.js                  # Main app with UI components
│   ├── App.css                 # Styling
│   ├── index.js                # React entry point
│   └── index.css               # Global styles
├── .env                        # Environment config (REACT_APP_GATEWAY_URL)
├── package.json                # Dependencies
├── mock-server.js              # Mock server for testing
├── launch-demo.sh              # Demo launcher script
└── README.md                   # Documentation
```

## Connection Configuration

### Environment Variable
```bash
REACT_APP_GATEWAY_URL=http://localhost:3001
```

### Socket.IO Client Settings
```javascript
{
  reconnection: true,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 10000,
  reconnectionAttempts: Infinity
}
```

## Expected Socket.IO Events

The frontend listens for the following events from the backend:

### 1. `shioaji_ready`
**Trigger:** Emitted once when backend service is ready
**Purpose:** Indicates service initialization complete

```javascript
{
  status: "ready",
  simulation: boolean,        // true if simulation mode
  version: string,            // e.g., "1.1.4"
  service_type: "market_data"
}
```

**Frontend Behavior:**
- Sets `serviceReady` state to `true`
- Displays "Service: Ready" indicator

---

### 2. `heartbeat`
**Trigger:** Emitted periodically (recommended: every 3-10 seconds)
**Purpose:** Service health and status monitoring

```javascript
{
  status: "running",
  shioaji_connected: boolean,
  gateway_connected: boolean,
  current_price: number,
  subscribed_contracts: number,
  timestamp: string           // ISO 8601 format
}
```

**Frontend Behavior:**
- Updates system status section
- Displays connection health indicators
- Shows current price and contract count

**Fallback Values:**
- If no data: displays `--` for all fields

---

### 3. `market_tick`
**Trigger:** Real-time on price updates
**Purpose:** Live OHLC tick data

```javascript
{
  exchange: "TAIFEX",
  code: string,               // e.g., "TXO24030018500C"
  datetime: string,           // e.g., "2026-03-04 09:00:00"
  open: number,
  high: number,
  low: number,
  close: number,
  price: number,              // Current price (same as close)
  volume: number,
  total_volume: number,
  timestamp: string           // ISO 8601 format
}
```

**Frontend Behavior:**
- Stores in `tickData` state by contract `code`
- Displays in TickCard component
- Shows OHLC prices
- Color-codes price (green if close >= open, red otherwise)
- Updates every tick

**Fallback Values:**
- Main price: `99999`
- OHLC values: `--`
- Volume: `--`
- Timestamp: `--:--:--`

---

### 4. `market_bidask`
**Trigger:** Real-time on order book updates
**Purpose:** Bid/Ask order book levels

```javascript
{
  exchange: "TAIFEX",
  code: string,
  datetime: string,
  bid_price: number[] | number,    // Array of levels or single value
  bid_volume: number[] | number,   // Corresponding volumes
  ask_price: number[] | number,
  ask_volume: number[] | number,
  timestamp: string
}
```

**Frontend Behavior:**
- Stores in `bidaskData` state by contract `code`
- Displays in OrderBookCard component
- Shows bid/ask levels with Chinese labels (買/賣)
- Supports both array (multiple levels) and single value formats

**Fallback Values:**
- Price/Volume: `--`
- Timestamp: `--:--:--`

---

### 5. `market_snapshot`
**Trigger:** Periodic (recommended: every 5 seconds)
**Purpose:** Market summary and daily statistics

```javascript
{
  code: string,
  name: string,               // e.g., "台指選擇權 202603 CALL 18500"
  open: number,
  high: number,
  low: number,
  close: number,
  volume: number,
  amount: number,
  total_volume: number,
  timestamp: string
}
```

**Frontend Behavior:**
- Stores in `snapshotData` state by contract `code`
- Displays in SnapshotCard component
- Shows daily high/low, total volume, amount

**Fallback Values:**
- All numeric fields: `--`

---

### 6. `python_error`
**Trigger:** On backend errors
**Purpose:** Error reporting and logging

```javascript
{
  error: string,
  message: string,
  timestamp: string
}
```

**Frontend Behavior:**
- Logs to console
- Can be used for error notifications (currently just logs)

---

## Frontend UI Components

### StatusIndicator
- Shows Socket connection status (Connected/Disconnected)
- Shows Service readiness (Ready/Not Ready)
- Colors: Green (online) / Red (offline)

### HeartbeatDisplay
- System status
- Current price
- Subscribed contracts count
- Shioaji and Gateway connection indicators

### TickCard
- Contract code and exchange
- Current price (large, color-coded)
- OHLC prices in grid
- Volume information
- Timestamp

### OrderBookCard
- Contract code
- Bid levels (green background)
- Ask levels (red background)
- Chinese labels: 買 (buy) / 賣 (sell)
- Timestamp

### SnapshotCard
- Contract code and name
- Daily OHLC summary
- Volume and amount statistics

## Placeholder Behavior

When backend is disconnected or no data is available:
- Shows 3 placeholder cards per section
- Main price displays: `99999`
- Other fields display: `--`
- Timestamps display: `--:--:--`
- Status indicators show: Red "Disconnected"

## Testing the Frontend

### With Mock Server (Included)
```bash
# Terminal 1
npm run mock-server

# Terminal 2
npm start
```

### With Your Backend
```bash
# Ensure your backend Socket.IO server runs on port 3001
# Then start frontend
npm start
```

### Demo Mode (iTerm)
```bash
npm run demo
```

---

## Integration Prompt for Backend

Use this prompt with your backend codebase:

```
I have a React frontend for real-time Taiwan options market data that expects
a Socket.IO server on port 3001.

Frontend repository: https://github.com/julian7862/dogbro-index-client

Please integrate my existing backend with this frontend by:

1. Reading the frontend API documentation in BACKEND_INTEGRATION_PROMPT.md
2. Ensuring the backend emits the following Socket.IO events in the correct format:
   - shioaji_ready (on startup)
   - heartbeat (every 3-10 seconds)
   - market_tick (real-time price updates)
   - market_bidask (order book updates)
   - market_snapshot (every 5 seconds)
   - python_error (on errors)

3. Configuring the Socket.IO server to:
   - Listen on port 3001
   - Allow CORS from http://localhost:3000
   - Handle multiple client connections
   - Support reconnection

4. Mapping my existing backend data structures to match the frontend's
   expected event formats as documented above.

The frontend is already complete and running. I just need my backend to
emit events in the correct format to the correct port.
```

---

## Quick Reference

| Aspect | Value |
|--------|-------|
| Frontend Port | 3000 |
| Backend Port Expected | 3001 |
| Protocol | Socket.IO |
| CORS Origin | http://localhost:3000 |
| Events to Emit | 6 (ready, heartbeat, tick, bidask, snapshot, error) |
| Reconnection | Auto (frontend handles) |
| Fallback Display | 99999 for prices, -- for others |
