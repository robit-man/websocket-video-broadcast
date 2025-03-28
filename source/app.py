#!/usr/bin/env python
"""
stream_forwarder.py

A Python script that:
  • Automatically creates and activates a virtual environment (if not already running in one),
  • Auto-generates a .env file (if one does not exist) with placeholder values for:
      - STREAM_PASSWORD (authentication),
      - WS_ENDPOINT (websocket signaling server endpoint),
      - VIDEO_FEED (local video stream route),
  • Prompts (or loads) configuration values for the video stream route, websocket endpoint, and password,
  • Saves the configuration to a file for future runs,
  • Connects to the signaling server via websockets,
      - Immediately sends an authentication JSON following the schema:
            {
              "type": "auth",
              "role": "source",
              "password": "secret"
            }
  • Opens the video stream (using OpenCV), encodes frames as JPEG (base64) and sends them as JSON messages,
  • Supports full stream forwarding with automatic reconnection.
"""

import os
import sys
import subprocess
import json

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

CONFIG_FILE = "config.json"
ENV_FILE = ".env"

def generate_env_file():
    """
    Auto-generates a .env file with placeholder values for:
      - STREAM_PASSWORD: Authentication password for the source.
      - WS_ENDPOINT: WebSocket signaling server endpoint.
      - VIDEO_FEED: Local video stream route.
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

async def stream_video(local_route, ws_endpoint, password):
    # Open the video capture once so that it remains active across reconnections.
    cap = cv2.VideoCapture(local_route)
    if not cap.isOpened():
        print("Error: Could not open video stream:", local_route)
        return
    
    try:
        while True:
            try:
                async with websockets.connect(ws_endpoint) as websocket:
                    # Send authentication message following the provided schema.
                    auth_msg = json.dumps({
                        "type": "auth",
                        "role": "source",
                        "password": password
                    })
                    await websocket.send(auth_msg)
                    
                    # Wait for server response (for demo purposes).
                    response = await websocket.recv()
                    print("Server response:", response)
                    
                    print("Starting video streaming...")
                    while True:
                        ret, frame = cap.read()
                        if not ret:
                            print("No frame received – end of stream or error.")
                            break
                        ret, buffer = cv2.imencode('.jpg', frame)
                        if not ret:
                            continue
                        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                        frame_msg = json.dumps({"frame": jpg_as_text})
                        await websocket.send(frame_msg)
                        # Sleep briefly to approximate a 30 fps stream.
                        await asyncio.sleep(0.033)
            except Exception as e:
                print("Exception during websocket communication:", e)
                print("Attempting to reconnect in 3 seconds...")
                await asyncio.sleep(3)
    finally:
        cap.release()

def main():
    # Auto-generate .env file if not present.
    generate_env_file()
    
    config = load_config()
    if "local_route" not in config:
        config["local_route"] = input("Enter local video route (e.g., /dev/video0 or video file path): ").strip()
    if "ws_endpoint" not in config:
        config["ws_endpoint"] = input("Enter websocket signaling server endpoint (e.g., ws://example.com:3000): ").strip()
    if "password" not in config:
        config["password"] = input("Enter stream password: ").strip()
    
    input("Press Enter to start streaming and save configuration...")
    save_config(config)
    print("Configuration saved to", CONFIG_FILE)
    
    asyncio.run(stream_video(config["local_route"], config["ws_endpoint"], config["password"]))

if __name__ == "__main__":
    main()
