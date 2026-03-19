# React Frontend Setup for DogBro Market Data

## Overview
This guide shows how to build a React.js frontend that connects to the market data service via Socket.IO for real-time Taiwan options market data.

## 1. Create React App

```bash
npx create-react-app dogbro-frontend
cd dogbro-frontend
npm install socket.io-client
```

## 2. Socket.IO Connection

### Install Dependencies
```bash
npm install socket.io-client
```

### Environment Variables
Create `.env` file:
```
REACT_APP_GATEWAY_URL=http://localhost:3001
```

## 3. Data Format Reference

The backend emits three main event types:

### Event: `market_tick`
Real-time tick data with OHLC prices:
```javascript
{
  exchange: "TAIFEX",           // Exchange code
  code: "TXO123456",            // Contract code
  datetime: "2024-03-04 09:00:00",
  open: 18500.0,
  high: 18520.0,
  low: 18490.0,
  close: 18510.0,
  price: 18510.0,               // Current price (same as close)
  volume: 100,
  total_volume: 5000,
  timestamp: "2024-03-04T09:00:00.123Z"
}
```

### Event: `market_bidask`
Bid/Ask order book data:
```javascript
{
  exchange: "TAIFEX",
  code: "TXO123456",
  datetime: "2024-03-04 09:00:00",
  bid_price: [18509.0, 18508.0, 18507.0],  // Best bid prices
  bid_volume: [10, 20, 30],                // Bid volumes
  ask_price: [18510.0, 18511.0, 18512.0],  // Best ask prices
  ask_volume: [15, 25, 35],                // Ask volumes
  timestamp: "2024-03-04T09:00:00.123Z"
}
```

### Event: `market_snapshot`
Snapshot data (emitted every 5 seconds):
```javascript
{
  code: "TXO123456",
  name: "台指選擇權 202403 CALL 18500",
  open: 18500.0,
  high: 18550.0,
  low: 18480.0,
  close: 18510.0,
  volume: 100,
  amount: 1850000.0,
  total_volume: 5000,
  timestamp: "2024-03-04T09:00:00.123Z"
}
```

### Event: `heartbeat`
Service health status (every 10 seconds):
```javascript
{
  status: "running",
  shioaji_connected: true,
  gateway_connected: true,
  current_price: 18510.0,        // Current index price
  subscribed_contracts: 16,      // Number of tracked contracts
  timestamp: "2024-03-04T09:00:00.123Z"
}
```

### Event: `shioaji_ready`
Service ready notification:
```javascript
{
  status: "ready",
  simulation: true,              // Simulation mode flag
  version: "1.1.4",             // Shioaji version
  service_type: "market_data"
}
```

## 4. React Implementation

### Create Socket Service (`src/services/socketService.js`)

```javascript
import { io } from 'socket.io-client';

class SocketService {
  constructor() {
    this.socket = null;
    this.connected = false;
  }

  connect(url = process.env.REACT_APP_GATEWAY_URL || 'http://localhost:3001') {
    this.socket = io(url, {
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 10000,
      reconnectionAttempts: Infinity
    });

    this.socket.on('connect', () => {
      console.log('Socket connected:', this.socket.id);
      this.connected = true;
    });

    this.socket.on('disconnect', () => {
      console.log('Socket disconnected');
      this.connected = false;
    });

    this.socket.on('connect_error', (error) => {
      console.error('Connection error:', error);
    });

    return this.socket;
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.connected = false;
    }
  }

  on(event, callback) {
    if (this.socket) {
      this.socket.on(event, callback);
    }
  }

  off(event, callback) {
    if (this.socket) {
      this.socket.off(event, callback);
    }
  }

  emit(event, data) {
    if (this.socket && this.connected) {
      this.socket.emit(event, data);
    }
  }

  isConnected() {
    return this.connected;
  }
}

export default new SocketService();
```

### Market Data Hook (`src/hooks/useMarketData.js`)

```javascript
import { useState, useEffect, useCallback } from 'react';
import socketService from '../services/socketService';

export const useMarketData = () => {
  const [tickData, setTickData] = useState({});
  const [bidaskData, setBidaskData] = useState({});
  const [snapshotData, setSnapshotData] = useState({});
  const [heartbeat, setHeartbeat] = useState(null);
  const [serviceReady, setServiceReady] = useState(false);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    // Connect to socket
    socketService.connect();

    // Connection status handlers
    const handleConnect = () => {
      console.log('Connected to market data service');
      setConnected(true);
    };

    const handleDisconnect = () => {
      console.log('Disconnected from market data service');
      setConnected(false);
      setServiceReady(false);
    };

    // Market data handlers
    const handleTick = (data) => {
      setTickData(prev => ({
        ...prev,
        [data.code]: data
      }));
    };

    const handleBidask = (data) => {
      setBidaskData(prev => ({
        ...prev,
        [data.code]: data
      }));
    };

    const handleSnapshot = (data) => {
      setSnapshotData(prev => ({
        ...prev,
        [data.code]: data
      }));
    };

    const handleHeartbeat = (data) => {
      setHeartbeat(data);
    };

    const handleReady = (data) => {
      console.log('Service ready:', data);
      setServiceReady(true);
    };

    const handleError = (data) => {
      console.error('Service error:', data);
    };

    // Register event listeners
    socketService.on('connect', handleConnect);
    socketService.on('disconnect', handleDisconnect);
    socketService.on('market_tick', handleTick);
    socketService.on('market_bidask', handleBidask);
    socketService.on('market_snapshot', handleSnapshot);
    socketService.on('heartbeat', handleHeartbeat);
    socketService.on('shioaji_ready', handleReady);
    socketService.on('python_error', handleError);

    // Cleanup
    return () => {
      socketService.off('connect', handleConnect);
      socketService.off('disconnect', handleDisconnect);
      socketService.off('market_tick', handleTick);
      socketService.off('market_bidask', handleBidask);
      socketService.off('market_snapshot', handleSnapshot);
      socketService.off('heartbeat', handleHeartbeat);
      socketService.off('shioaji_ready', handleReady);
      socketService.off('python_error', handleError);
      socketService.disconnect();
    };
  }, []);

  return {
    tickData,
    bidaskData,
    snapshotData,
    heartbeat,
    serviceReady,
    connected
  };
};
```

### Main Component Example (`src/App.js`)

```javascript
import React from 'react';
import { useMarketData } from './hooks/useMarketData';
import './App.css';

function App() {
  const {
    tickData,
    bidaskData,
    snapshotData,
    heartbeat,
    serviceReady,
    connected
  } = useMarketData();

  return (
    <div className="App">
      <header className="App-header">
        <h1>DogBro Market Data</h1>
        <div className="status">
          <StatusIndicator
            connected={connected}
            serviceReady={serviceReady}
          />
        </div>
      </header>

      <main>
        {/* Heartbeat Monitor */}
        <section className="heartbeat-section">
          <h2>System Status</h2>
          {heartbeat && <HeartbeatDisplay data={heartbeat} />}
        </section>

        {/* Real-time Tick Data */}
        <section className="tick-section">
          <h2>Live Tick Data</h2>
          <div className="data-grid">
            {Object.values(tickData).map(tick => (
              <TickCard key={tick.code} data={tick} />
            ))}
          </div>
        </section>

        {/* Order Book (Bid/Ask) */}
        <section className="orderbook-section">
          <h2>Order Book</h2>
          <div className="data-grid">
            {Object.values(bidaskData).map(bidask => (
              <OrderBookCard key={bidask.code} data={bidask} />
            ))}
          </div>
        </section>

        {/* Snapshots */}
        <section className="snapshot-section">
          <h2>Market Snapshots</h2>
          <div className="data-grid">
            {Object.values(snapshotData).map(snapshot => (
              <SnapshotCard key={snapshot.code} data={snapshot} />
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

// Status Indicator Component
const StatusIndicator = ({ connected, serviceReady }) => (
  <div className="status-indicator">
    <div className={`indicator ${connected ? 'online' : 'offline'}`}>
      Socket: {connected ? 'Connected' : 'Disconnected'}
    </div>
    <div className={`indicator ${serviceReady ? 'online' : 'offline'}`}>
      Service: {serviceReady ? 'Ready' : 'Not Ready'}
    </div>
  </div>
);

// Heartbeat Display Component
const HeartbeatDisplay = ({ data }) => (
  <div className="heartbeat-card">
    <div className="stat">
      <label>Status:</label>
      <span>{data.status}</span>
    </div>
    <div className="stat">
      <label>Current Price:</label>
      <span>{data.current_price?.toFixed(2) || 'N/A'}</span>
    </div>
    <div className="stat">
      <label>Subscribed Contracts:</label>
      <span>{data.subscribed_contracts}</span>
    </div>
    <div className="stat">
      <label>Shioaji:</label>
      <span className={data.shioaji_connected ? 'online' : 'offline'}>
        {data.shioaji_connected ? '✓' : '✗'}
      </span>
    </div>
    <div className="stat">
      <label>Gateway:</label>
      <span className={data.gateway_connected ? 'online' : 'offline'}>
        {data.gateway_connected ? '✓' : '✗'}
      </span>
    </div>
  </div>
);

// Tick Card Component
const TickCard = ({ data }) => {
  const priceColor = data.close >= data.open ? 'green' : 'red';

  return (
    <div className="tick-card">
      <div className="card-header">
        <h3>{data.code}</h3>
        <span className="exchange">{data.exchange}</span>
      </div>
      <div className="price-info">
        <div className={`current-price ${priceColor}`}>
          {data.price?.toFixed(2) || 'N/A'}
        </div>
        <div className="ohlc">
          <span>O: {data.open?.toFixed(2)}</span>
          <span>H: {data.high?.toFixed(2)}</span>
          <span>L: {data.low?.toFixed(2)}</span>
          <span>C: {data.close?.toFixed(2)}</span>
        </div>
      </div>
      <div className="volume-info">
        <div>Vol: {data.volume}</div>
        <div>Total: {data.total_volume}</div>
      </div>
      <div className="timestamp">
        {new Date(data.timestamp).toLocaleTimeString()}
      </div>
    </div>
  );
};

// Order Book Card Component
const OrderBookCard = ({ data }) => (
  <div className="orderbook-card">
    <div className="card-header">
      <h3>{data.code}</h3>
    </div>
    <div className="orderbook">
      <div className="asks">
        <h4>Ask (賣)</h4>
        {Array.isArray(data.ask_price) ? (
          data.ask_price.map((price, idx) => (
            <div key={idx} className="order-level ask">
              <span className="price">{price?.toFixed(2)}</span>
              <span className="volume">{data.ask_volume[idx]}</span>
            </div>
          ))
        ) : (
          <div className="order-level ask">
            <span className="price">{data.ask_price?.toFixed(2)}</span>
            <span className="volume">{data.ask_volume}</span>
          </div>
        )}
      </div>
      <div className="bids">
        <h4>Bid (買)</h4>
        {Array.isArray(data.bid_price) ? (
          data.bid_price.map((price, idx) => (
            <div key={idx} className="order-level bid">
              <span className="price">{price?.toFixed(2)}</span>
              <span className="volume">{data.bid_volume[idx]}</span>
            </div>
          ))
        ) : (
          <div className="order-level bid">
            <span className="price">{data.bid_price?.toFixed(2)}</span>
            <span className="volume">{data.bid_volume}</span>
          </div>
        )}
      </div>
    </div>
    <div className="timestamp">
      {new Date(data.timestamp).toLocaleTimeString()}
    </div>
  </div>
);

// Snapshot Card Component
const SnapshotCard = ({ data }) => (
  <div className="snapshot-card">
    <div className="card-header">
      <h3>{data.code}</h3>
      <p className="contract-name">{data.name}</p>
    </div>
    <div className="price-summary">
      <div>Open: {data.open?.toFixed(2)}</div>
      <div>High: {data.high?.toFixed(2)}</div>
      <div>Low: {data.low?.toFixed(2)}</div>
      <div>Close: {data.close?.toFixed(2)}</div>
    </div>
    <div className="volume-summary">
      <div>Volume: {data.volume}</div>
      <div>Amount: {data.amount?.toLocaleString()}</div>
      <div>Total Vol: {data.total_volume}</div>
    </div>
  </div>
);

export default App;
```

### Basic Styling (`src/App.css`)

```css
.App {
  min-height: 100vh;
  background: #1a1a2e;
  color: #eee;
}

.App-header {
  background: #16213e;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.3);
}

.App-header h1 {
  margin: 0 0 10px 0;
  color: #00d9ff;
}

.status-indicator {
  display: flex;
  gap: 15px;
  margin-top: 10px;
}

.indicator {
  padding: 5px 15px;
  border-radius: 20px;
  font-size: 14px;
}

.indicator.online {
  background: #00ff88;
  color: #000;
}

.indicator.offline {
  background: #ff4444;
  color: #fff;
}

main {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

section {
  margin-bottom: 40px;
}

section h2 {
  color: #00d9ff;
  border-bottom: 2px solid #00d9ff;
  padding-bottom: 10px;
  margin-bottom: 20px;
}

.data-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

.tick-card, .orderbook-card, .snapshot-card, .heartbeat-card {
  background: #16213e;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.3);
  transition: transform 0.2s;
}

.tick-card:hover, .orderbook-card:hover, .snapshot-card:hover {
  transform: translateY(-5px);
}

.card-header h3 {
  margin: 0 0 5px 0;
  color: #00d9ff;
  font-size: 18px;
}

.exchange, .contract-name {
  color: #aaa;
  font-size: 12px;
}

.current-price {
  font-size: 32px;
  font-weight: bold;
  margin: 15px 0;
}

.current-price.green {
  color: #00ff88;
}

.current-price.red {
  color: #ff4444;
}

.ohlc {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 10px 0;
  font-size: 12px;
}

.volume-info, .price-summary, .volume-summary {
  display: flex;
  justify-content: space-between;
  margin: 10px 0;
  padding: 10px 0;
  border-top: 1px solid #2a3f5f;
  font-size: 13px;
}

.timestamp {
  text-align: right;
  color: #888;
  font-size: 11px;
  margin-top: 10px;
}

.orderbook {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin: 15px 0;
}

.order-level {
  display: flex;
  justify-content: space-between;
  padding: 5px 10px;
  margin: 3px 0;
  border-radius: 5px;
}

.order-level.ask {
  background: rgba(255, 68, 68, 0.2);
}

.order-level.bid {
  background: rgba(0, 255, 136, 0.2);
}

.heartbeat-card .stat {
  display: flex;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid #2a3f5f;
}

.heartbeat-card .stat:last-child {
  border-bottom: none;
}

.online {
  color: #00ff88;
}

.offline {
  color: #ff4444;
}
```

## 5. Running the Application

### Start the Backend (Market Data Service)
```bash
# In dogbro-index-api directory
python -m src.main
```

### Start the React Frontend
```bash
# In dogbro-frontend directory
npm start
```

The app will open at `http://localhost:3000` and automatically connect to the Socket.IO gateway at `http://localhost:3001`.

## 6. Key Features

- **Real-time Updates**: Automatic updates via Socket.IO
- **Auto-Reconnection**: Handles connection drops gracefully
- **Multiple Data Streams**: Tick, BidAsk, and Snapshot data
- **Health Monitoring**: Heartbeat and status indicators
- **Responsive Grid**: Adapts to different screen sizes

## 7. Architecture Overview

```
React App (Port 3000)
     |
     | Socket.IO
     ↓
Node.js Gateway (Port 3001)
     |
     | Socket.IO
     ↓
Python Market Data Service
     |
     | Shioaji API
     ↓
Taiwan Stock Exchange
```

## 8. Next Steps

1. Add authentication if needed
2. Implement data visualization (charts)
3. Add filtering and search for contracts
4. Implement trading features
5. Add notifications for price alerts
6. Store historical data
