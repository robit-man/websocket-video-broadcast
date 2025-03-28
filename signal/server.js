// server.js
require('dotenv').config();
const express = require('express');
const http = require('http');
const WebSocket = require('ws');

const app = express();
const server = http.createServer(app);
const port = process.env.PORT || 3000;

// Set the required password via environment variable; fallback if not provided.
const REQUIRED_PASSWORD = process.env.PASSWORD || "secret";

// Create the WebSocket server on top of our HTTP server
const wss = new WebSocket.Server({ server });

// Variables to track the video source and connected peers
let videoSource = null;
const peers = new Set();

// Keep track of the last reported source->server latency
let sourceLatencyMs = 0;

// Data metrics counters (for logging throughput)
let totalSourceBytes = 0;
let totalForwardedBytes = 0;
let lastTime = Date.now();

// Periodically log data rate metrics (every 5 seconds)
setInterval(() => {
  const now = Date.now();
  const deltaTimeSec = (now - lastTime) / 1000;
  const sourceRate = totalSourceBytes / deltaTimeSec;
  const forwardedRate = totalForwardedBytes / deltaTimeSec;
  console.log(
    `Data rate (last ${deltaTimeSec.toFixed(2)} sec): ` +
    `Source -> Server: ${sourceRate.toFixed(2)} B/s, ` +
    `Server -> Peers: ${forwardedRate.toFixed(2)} B/s`
  );
  totalSourceBytes = 0;
  totalForwardedBytes = 0;
  lastTime = now;
}, 5000);

wss.on('connection', (ws) => {
  ws.isAuthenticated = false;
  ws.role = null;

  // Each peer will store its own "server->peer" latency here
  ws.serverToPeerLatencyMs = 0;

  ws.on('message', (message, isBinary) => {
    // If not authenticated, expect an authentication message first.
    if (!ws.isAuthenticated) {
      try {
        const data = JSON.parse(message.toString());
        if (data.type === 'auth' && data.password) {
          // Check the provided password
          if (data.password === REQUIRED_PASSWORD) {
            ws.isAuthenticated = true;
            // Handle role: "source" or "peer"
            if (data.role === 'source') {
              // Only allow one video source at a time
              if (videoSource) {
                ws.send(JSON.stringify({ type: 'error', message: 'Video source already connected.' }));
                ws.close();
                return;
              }
              ws.role = 'source';
              videoSource = ws;
              ws.send(JSON.stringify({ type: 'info', message: 'Authenticated as video source.' }));
              console.log('Video source connected.');
            } else if (data.role === 'peer') {
              ws.role = 'peer';
              peers.add(ws);
              ws.send(JSON.stringify({ type: 'info', message: 'Authenticated as peer.' }));
              console.log('Peer connected.');
            } else {
              ws.send(JSON.stringify({ type: 'error', message: 'Invalid role specified. Use "source" or "peer".' }));
              ws.close();
            }
          } else {
            ws.send(JSON.stringify({ type: 'error', message: 'Invalid password.' }));
            ws.close();
          }
        } else {
          ws.send(JSON.stringify({ type: 'error', message: 'Authentication required.' }));
          ws.close();
        }
      } catch (err) {
        ws.send(JSON.stringify({ type: 'error', message: 'Invalid authentication format.' }));
        ws.close();
      }
      return; // Done processing if not authenticated
    }

    // ---------- Already Authenticated ----------
    if (ws.role === 'source') {
      // Forward frames from source to peers
      const bytes = isBinary
        ? message.length
        : Buffer.byteLength(message.toString(), 'utf8');
      totalSourceBytes += bytes;

      for (let peer of peers) {
        if (peer.readyState === WebSocket.OPEN) {
          peer.send(message, { binary: isBinary });
          totalForwardedBytes += bytes;
        }
      }
    }

    // Parse JSON to handle pings/latency reports
    let data;
    try {
      data = JSON.parse(message.toString());
    } catch (err) {
      // Not JSON or not relevant, ignore
      return;
    }

    if (data.type === 'ping') {
      // Echo back with "pong" plus same timestamp
      ws.send(JSON.stringify({
        type: 'pong',
        timestamp: data.timestamp
      }));
    } else if (data.type === 'latencyReport') {
      // The sender is reporting its measured round-trip time
      if (ws.role === 'source') {
        // Update global source->server latency
        sourceLatencyMs = data.latency;
      } else if (ws.role === 'peer') {
        // Update this peer's server->peer latency
        ws.serverToPeerLatencyMs = data.latency;
        // Send both latencies back to just this peer
        ws.send(JSON.stringify({
          type: 'metricsUpdate',
          sourceToServerLatency: sourceLatencyMs,
          serverToPeerLatency: ws.serverToPeerLatencyMs
        }));
      }
    }
  });

  ws.on('close', () => {
    if (ws.role === 'source') {
      videoSource = null;
      console.log('Video source disconnected.');
    }
    if (ws.role === 'peer') {
      peers.delete(ws);
      console.log('Peer disconnected.');
    }
  });
});

server.listen(port, () => {
  console.log(`Server is listening on port ${port}`);
});
