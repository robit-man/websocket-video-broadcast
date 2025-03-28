#!/usr/bin/env python
"""
stream_forwarder.py

- Creates/activates a venv (if not already in one).
- Auto-generates a .env if not present.
- Loads/saves config from config.json.
- Connects via websockets, sends authentication, streams frames from OpenCV.
- Measures round-trip latency with ping/pong, dynamically adjusts JPEG quality.
- Reports latency back to the signaling server.
- Implements exponential backoff on errors.
- If video capture fails, the script restarts entirely to refresh the local video stream.
"""

import os
import sys
import subprocess
import json

# Function to completely restart the script
def restart_script():
    print("Restarting the script entirely to refresh video capture...")
    python = sys.executable
    os.execv(python, [python] + sys.argv)

# Auto-create and re-run in a virtual environment if not already in one.
if sys.prefix == sys.base_prefix:
    venv_dir = os.path.join(os.getcwd(), 'venv')
    if not os.path.exists(venv_dir):
        subprocess.check_call([sys.executable, "-m", "venv", "venv"])
    venv_python = os.path.join(venv_dir, "Scripts", "python.exe") if os.name == "nt" else os.path.join(venv_dir, "bin", "python")
    subprocess.check_call([venv_python] + sys.argv)
    sys.exit(0)

# Ensure required packages are available.
try:
    import cv2
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "opencv-python"])
    import cv2

try:
    import websockets
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets

import asyncio
import base64
import time

CONFIG_FILE = "config.json"
ENV_FILE = ".env"

def generate_env_file():
    """
    Auto-generates a .env file with placeholder values for:
      - STREAM_PASSWORD
      - WS_ENDPOINT
      - VIDEO_FEED
    """
    if not os.path.exists(ENV_FILE):
        placeholders = [
            "# Auto-generated .env file for stream_forwarder.py",
            "# Please replace the placeholder values as needed",
            "STREAM_PASSWORD=your_password_here",
            "WS_ENDPOINT=ws://example.com:3000",
            "VIDEO_FEED=/dev/video0"
        ]
        with open(ENV_FILE, "w") as f:
            f.write("\n".join(placeholders))
        print(f"{ENV_FILE} file created with placeholder values.")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    else:
        config = {}
    return config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

async def handle_server_messages(websocket, state):
    """
    Continuously read messages from the server in a separate task.
    - We specifically look for 'pong' messages to calculate round-trip latency.
    """
    while True:
        try:
            msg = await websocket.recv()
        except websockets.exceptions.ConnectionClosed:
            print("Server connection closed while reading messages.")
            return

        try:
            data = json.loads(msg)
        except:
            continue  # Not JSON, ignore

        if data.get("type") == "pong":
            # Measure round-trip time
            send_ts = data.get("timestamp")
            if send_ts is not None:
                now = time.time()
                rtt_ms = (now - send_ts) * 1000.0
                state["latency_ms"] = rtt_ms

                # Send a "latencyReport" to the server
                latency_report = {
                    "type": "latencyReport",
                    "latency": rtt_ms
                }
                await websocket.send(json.dumps(latency_report))

                # Adjust compression quality if latency is too high/low (keep within [10..95])
                if rtt_ms > 200 and state["jpeg_quality"] > 10:
                    state["jpeg_quality"] -= 10
                    print(f"High latency ({rtt_ms:.1f} ms). Lowering JPEG quality to {state['jpeg_quality']}")
                elif rtt_ms < 100 and state["jpeg_quality"] < 70:
                    state["jpeg_quality"] += 10
                    print(f"Low latency ({rtt_ms:.1f} ms). Raising JPEG quality to {state['jpeg_quality']}")

async def send_frames(websocket, cap, state):
    """
    Continuously read frames from the camera, encode them, and send to server.
    Also periodically send 'ping' messages to measure latency.
    """
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("No frame received – end of stream or error.")
            # Force an exception to trigger a full restart of the script.
            raise RuntimeError("Video capture read failed.")

        # Encode frame as JPEG with current quality
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), state["jpeg_quality"]]
        ret, buffer = cv2.imencode('.jpg', frame, encode_param)
        if not ret:
            # If encoding fails, skip this frame
            continue

        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
        frame_msg = json.dumps({"frame": jpg_as_text})
        await websocket.send(frame_msg)

        # Periodically send "ping" to measure round-trip latency
        frame_count += 1
        if frame_count % 30 == 0:
            ping_msg = {
                "type": "ping",
                "timestamp": time.time()
            }
            await websocket.send(json.dumps(ping_msg))

        # Sleep to roughly target ~30 fps
        await asyncio.sleep(0.033)

async def stream_video(local_route, ws_endpoint, password):
    """
    Opens the local video feed, connects to the WebSocket, sends frames.
    Implements exponential backoff on errors and dynamic compression.
    If video capture fails, the entire script is restarted.
    """
    # Attempt to open the video capture. If it fails initially, exit.
    cap = cv2.VideoCapture(local_route)
    if not cap.isOpened():
        print("Error: Could not open video stream:", local_route)
        return

    # Shared state for dynamic compression and latency metrics.
    state = {
        "jpeg_quality": 70,   # Start with mid-range JPEG quality.
        "latency_ms": 0.0
    }

    backoff_seconds = 3
    max_backoff = 60  # Cap the backoff at 60 seconds

    while True:
        try:
            async with websockets.connect(ws_endpoint) as websocket:
                # Reset backoff after a successful connection.
                backoff_seconds = 3

                # Send authentication.
                auth_msg = json.dumps({
                    "type": "auth",
                    "role": "source",
                    "password": password
                })
                await websocket.send(auth_msg)

                # Read and print server's initial response.
                response = await websocket.recv()
                print("Server response:", response)

                print("Starting video streaming...")

                # Create two tasks:
                # 1) Read messages from the server.
                # 2) Send frames to the server.
                consumer_task = asyncio.create_task(handle_server_messages(websocket, state))
                producer_task = asyncio.create_task(send_frames(websocket, cap, state))

                # Wait until one of them finishes (which should happen on error).
                done, pending = await asyncio.wait(
                    [consumer_task, producer_task],
                    return_when=asyncio.FIRST_EXCEPTION
                )

                # Cancel any pending tasks.
                for task in pending:
                    task.cancel()

                # If an exception was raised, re-raise it.
                for task in done:
                    if task.exception():
                        raise task.exception()

        except Exception as e:
            print("Exception during websocket communication:", e)
            # If the exception is due to video capture failure, restart the entire script.
            if "Video capture read failed" in str(e):
                print("Detected video capture failure. Restarting script entirely...")
                restart_script()
            else:
                print(f"Attempting to reconnect in {backoff_seconds} seconds...")
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, max_backoff)

    # Cleanup (this code is unlikely to be reached due to the infinite loop).
    cap.release()

def main():
    generate_env_file()

    config = load_config()
    if "local_route" not in config:
        config["local_route"] = input("Enter local video route (e.g., /dev/video0 or video file path): ").strip()
    if "ws_endpoint" not in config:
        config["ws_endpoint"] = input("Enter websocket signaling server endpoint (e.g., ws://example.com:3000): ").strip()
    if "password" not in config:
        config["password"] = input("Enter stream password: ").strip()

    save_config(config)
    print("Configuration saved to", CONFIG_FILE)

    # Start the streaming process.
    asyncio.run(stream_video(config["local_route"], config["ws_endpoint"], config["password"]))

if __name__ == "__main__":
    main()
