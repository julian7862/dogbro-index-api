// -----------------------------------------------------------
// WebSocket Hub - 純粹的 Socket.IO 事件中繼伺服器
// -----------------------------------------------------------
const express = require("express");

const app = express();
const PORT = process.env.PORT || 3001;

/* =========================================================
 * 1. JSON 解析中介層
 * ======================================================= */
app.use(express.json());

/* =========================================================
 * 2. 健康檢查端點
 * ======================================================= */
app.get("/healthz", (_, res) => {
  res.json({
    status: "ok",
    service: "websocket-hub",
    timestamp: new Date().toISOString()
  });
});

/* =========================================================
 * 3. Socket.IO：純粹的事件中繼
 * ======================================================= */
const http = require("http").createServer(app);
const io = require("socket.io")(http, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

const normalizeIVIndicatorPayload = (payload = {}) => ({
  civ: payload.civ ?? null,
  civ_ma5: payload.civ_ma5 ?? null,
  civ_pb: payload.civ_pb ?? null,
  price_pb: payload.price_pb ?? null,
  pb_minus_civ_pb: payload.pb_minus_civ_pb ?? payload.signal ?? null,
  signal: payload.signal ?? payload.pb_minus_civ_pb ?? null,
  dte: payload.dte ?? null,
  valid_call_iv_count: payload.valid_call_iv_count ?? null,
  current_dt: payload.current_dt ?? payload.timestamp ?? null,
  timestamp: payload.timestamp ?? payload.current_dt ?? null
});

// 儲存最新狀態
let latestReadyStatus = null;
let latestHeartbeat = null;
let latestOptionMetadata = null;
let latestSnapshots = {}; // code -> snapshot data
let latestKbarClose = null; // 最新 5 分 K 收盤
let latestIVIndicator = null; // 最新 IV 指標

io.on("connection", (socket) => {
  console.log(`[Socket] 客戶端已連線：${socket.id}`);

  // 發送最新狀態給新連線的客戶端
  if (latestReadyStatus) {
    socket.emit('shioaji_ready', latestReadyStatus);
    console.log(`[發送快取] shioaji_ready 給 ${socket.id}`);
  }
  if (latestHeartbeat) {
    socket.emit('heartbeat', latestHeartbeat);
  }
  if (latestOptionMetadata) {
    socket.emit('option_metadata', latestOptionMetadata);
    console.log(`[發送快取] option_metadata 給 ${socket.id}`);
  }
  // 發送所有快取的 snapshots
  const snapshotKeys = Object.keys(latestSnapshots);
  if (snapshotKeys.length > 0) {
    console.log(`[發送快取] ${snapshotKeys.length} 個 snapshots 給 ${socket.id}`);
    snapshotKeys.forEach(code => {
      socket.emit('market_snapshot', latestSnapshots[code]);
    });
  }
  // 發送快取的 kbar_close
  if (latestKbarClose) {
    socket.emit('kbar_close', latestKbarClose);
    console.log(`[發送快取] kbar_close 給 ${socket.id}`);
  }
  // 發送快取的 iv_indicator
  if (latestIVIndicator) {
    socket.emit('iv_indicator', latestIVIndicator);
    console.log(`[發送快取] iv_indicator 給 ${socket.id}`);
  }

  /* 轉送所有事件（廣播給所有客戶端） */
  socket.onAny((event, ...args) => {
    console.log(`[中繼] ${event}:`, args);

    // 儲存重要狀態
    if (event === 'shioaji_ready' && args[0]) {
      latestReadyStatus = args[0];
    } else if (event === 'heartbeat' && args[0]) {
      latestHeartbeat = args[0];
    } else if (event === 'option_metadata' && args[0]) {
      latestOptionMetadata = args[0];
    } else if (event === 'market_snapshot' && args[0]?.code) {
      latestSnapshots[args[0].code] = args[0];
    } else if (event === 'kbar_close' && args[0]) {
      latestKbarClose = args[0];
    } else if (event === 'iv_indicator' && args[0]) {
      latestIVIndicator = normalizeIVIndicatorPayload(args[0]);
      args[0] = latestIVIndicator;
    }

    // 使用 io.emit 廣播給所有客戶端（包括發送者）
    io.emit(event, ...args);
  });

  socket.on("disconnect", () => {
    console.log(`[Socket] 客戶端已斷線：${socket.id}`);
  });
});

/* =========================================================
 * 4. 伺服器啟動
 * ======================================================= */
if (require.main === module) {
  http.listen(PORT, () => {
    console.log("=".repeat(60));
    console.log(`[WebSocket Hub] 運行於 http://0.0.0.0:${PORT}`);
    console.log(`[WebSocket Hub] Socket.IO 中繼已啟用`);
    console.log("=".repeat(60));
  });
}

/* =========================================================
 * 5. 優雅關閉處理
 * ======================================================= */
const shutdown = (signal) => {
  console.log(`\n[WebSocket Hub] 收到 ${signal}，正在關閉...`);
  http.close(() => {
    console.log("[WebSocket Hub] 伺服器已關閉");
    process.exit(0);
  });
};

if (require.main === module) {
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

module.exports = {
  normalizeIVIndicatorPayload
};
