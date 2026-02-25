const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

const PORT = process.env.PORT || 3001;
let pyProc = null;

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    pythonRunning: pyProc !== null,
    timestamp: new Date().toISOString()
  });
});

// Socket.io relay logic - broadcast all events
io.on('connection', (socket) => {
  console.log(`[Socket] Client connected: ${socket.id}`);

  // Relay all events to all other clients
  socket.onAny((event, ...args) => {
    console.log(`[Relay] ${event}:`, args);
    socket.broadcast.emit(event, ...args);
  });

  socket.on('disconnect', () => {
    console.log(`[Socket] Client disconnected: ${socket.id}`);
  });
});

/**
 * Start Python process with hot restart support
 */
function startPython() {
  // Kill existing process if running
  if (pyProc) {
    console.log('[Python] Stopping existing Python process...');
    pyProc.kill();
    pyProc = null;
  }

  const pythonPath = path.resolve(__dirname, '../main.py');
  const pythonBin = path.resolve(__dirname, '../venv/bin/python');

  console.log(`[Python] Starting Python process: ${pythonPath}`);
  console.log(`[Python] Using Python binary: ${pythonBin}`);

  pyProc = spawn(pythonBin, [pythonPath], {
    env: { ...process.env },
    cwd: path.resolve(__dirname, '..')
  });

  pyProc.stdout.on('data', (data) => {
    console.log(`[Python stdout] ${data.toString().trim()}`);
  });

  pyProc.stderr.on('data', (data) => {
    console.error(`[Python stderr] ${data.toString().trim()}`);
  });

  pyProc.on('close', (code) => {
    console.log(`[Python] Process exited with code ${code}`);
    pyProc = null;
  });

  pyProc.on('error', (err) => {
    console.error(`[Python] Failed to start:`, err);
    pyProc = null;
  });

  return pyProc;
}

/**
 * API endpoint to set Shioaji credentials and restart Python
 */
app.post('/set-sj-key', async (req, res) => {
  try {
    const { apiKey, secretKey, caCertPath, caPassword } = req.body;

    if (!apiKey || !secretKey || !caCertPath || !caPassword) {
      return res.status(400).json({
        error: 'Missing required fields: apiKey, secretKey, caCertPath, caPassword'
      });
    }

    // Write to /tmp/.env
    const envContent = `API_KEY=${apiKey}
SECRET_KEY=${secretKey}
CA_CERT_PATH=${caCertPath}
CA_PASSWORD=${caPassword}
`;

    fs.writeFileSync('/tmp/.env', envContent, 'utf8');
    console.log('[Config] Credentials written to /tmp/.env');

    // Restart Python process
    startPython();

    res.json({
      success: true,
      message: 'Credentials updated and Python process restarted'
    });
  } catch (error) {
    console.error('[Config] Error:', error);
    res.status(500).json({
      error: 'Failed to update credentials',
      details: error.message
    });
  }
});

/**
 * Manual Python restart endpoint
 */
app.post('/restart-python', (req, res) => {
  try {
    startPython();
    res.json({
      success: true,
      message: 'Python process restarted'
    });
  } catch (error) {
    res.status(500).json({
      error: 'Failed to restart Python',
      details: error.message
    });
  }
});

// Start server
server.listen(PORT, () => {
  console.log(`[Gateway] Server running on http://localhost:${PORT}`);
  console.log(`[Gateway] Socket.io relay active`);

  // Auto-start Python on server startup
  startPython();
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('[Gateway] SIGTERM received, shutting down...');
  if (pyProc) {
    pyProc.kill();
  }
  server.close(() => {
    console.log('[Gateway] Server closed');
    process.exit(0);
  });
});
