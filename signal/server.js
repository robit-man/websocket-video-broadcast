// Load environment variables from .env file
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

// Data metrics counters
let totalSourceBytes = 0;
let totalForwardedBytes = 0;
let lastTime = Date.now();

// Periodically log data rate metrics (every 5 seconds)
setInterval(() => {
  const now = Date.now();
  const deltaTimeSec = (now - lastTime) / 1000;
  const sourceRate = totalSourceBytes / deltaTimeSec;
  const forwardedRate = totalForwardedBytes / deltaTimeSec;
  console.log(`Data rate (last ${deltaTimeSec.toFixed(2)} sec): Source -> Server: ${sourceRate.toFixed(2)} B/s, Server -> Peers: ${forwardedRate.toFixed(2)} B/s`);
  totalSourceBytes = 0;
  totalForwardedBytes = 0;
  lastTime = now;
}, 5000);

// On each new WebSocket connection...
wss.on('connection', (ws) => {
  // Initially mark the connection as not authenticated
  ws.isAuthenticated = false;
  ws.role = null;

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
    } else {
      // Already authenticated: if the client is the video source, forward the data to all connected peers.
      if (ws.role === 'source') {
        // Calculate byte size of the incoming message.
        const bytes = isBinary ? message.length : Buffer.byteLength(message.toString(), 'utf8');
        totalSourceBytes += bytes;

        // Forward the message to each peer and track the forwarded bytes.
        for (let peer of peers) {
          if (peer.readyState === WebSocket.OPEN) {
            peer.send(message, { binary: isBinary });
            totalForwardedBytes += bytes;
          }
        }
      }
      // Additional commands from peers can be handled here if needed.
    }
  });

  ws.on('close', () => {
    // Clean up on disconnect
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

// Start the server
server.listen(port, () => {
  console.log(`Server is listening on port ${port}`);
});
