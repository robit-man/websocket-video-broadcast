# Video Stream Forwarding System

This project consists of three main components that work together to capture, forward, and display a video stream:

1. **Stream Forwarder (Python):**  
   Captures video from a local source (e.g. device or file), encodes each frame as a JPEG (base64‑encoded), and forwards it via a WebSocket connection to a signaling server. This script auto‑generates a `.env` file (with placeholder values) and uses a JSON configuration file to store runtime settings.

2. **Signaling Server (Node.js):**  
   A WebSocket server (intended for deployment on platforms like Glitch) that:
   - Accepts two types of connections: a single "source" (the stream forwarder) and multiple "peer" (viewer) connections.
   - Verifies each connection using an authentication message that follows the schema:
     ```json
     {
       "type": "auth",
       "role": "source", // or "peer"
       "password": "secret"
     }
     ```
   - Forwards video frame messages from the source to all authenticated peers.

3. **Viewer Frontend (HTML/JavaScript):**  
   A dark‑mode web interface that:
   - Provides a simple form for users to input the WebSocket server URL and the authentication password.
   - Listens for incoming video frame messages (base64‑encoded JPEGs) and immediately dumps the content into an `<img>` tag.
   - Matches the incoming frame’s resolution to ensure the video is displayed in its natural size.

---

## Component Details

### 1. Stream Forwarder (Python)
- **File:** `stream_forwarder.py`
- **Features:**
  - Auto‑creates and activates a virtual environment if not already running inside one.
  - Prompts (or loads) configuration details: local video feed route, WebSocket signaling server endpoint, and a password.
  - Auto‑generates a `.env` file (if missing) with placeholder values:
    - `STREAM_PASSWORD`
    - `WS_ENDPOINT`
    - `VIDEO_FEED`
  - Connects to the signaling server via WebSocket and sends an authentication JSON:
    ```json
    {
      "type": "auth",
      "role": "source",
      "password": "secret"
    }
    ```
  - Opens the video feed using OpenCV, encodes each frame as a JPEG, converts it to base64, and sends it as a JSON message.
  - Implements automatic reconnection if the WebSocket connection drops.
- **Usage:**
  - Run the script with:  
    ```bash
    python stream_forwarder.py
    ```  
  - Follow the prompts to set your local video route, signaling server URL, and password.  
  - The configuration is saved for subsequent runs.

---

### 2. Signaling Server (Node.js)
- **File:** `server.js`
- **Features:**
  - Uses Node.js with the [ws](https://www.npmjs.com/package/ws) and [dotenv](https://www.npmjs.com/package/dotenv) libraries.
  - Loads a required password from a `.env` file (e.g., `STREAM_PASSWORD=your_password_here`).
  - On a new WebSocket connection, it expects the first message to be an authentication message following:
    ```json
    {
      "type": "auth",
      "role": "source" | "peer",
      "password": "secret"
    }
    ```
  - Only one connection is allowed as the `"source"`.
  - Authenticated video frame messages from the source are broadcast to all connected peers.
- **Usage:**
  - Deploy this script on a Node.js host (such as [Glitch](https://glitch.com)).
  - Ensure you have a `.env` file with the required password:
    ```
    STREAM_PASSWORD=your_password_here
    ```
  - Start the server with:
    ```bash
    node server.js
    ```

---

### 3. Viewer Frontend (HTML/JavaScript)
- **File:** `index.html`
- **Features:**
  - Provides a user-friendly, dark‑mode interface.
  - Contains a simple form to enter the WebSocket server URL and password.
  - Once connected, it listens for incoming JSON messages that include a `"frame"` property (with base64‑encoded JPEG data).
  - Instantly updates an `<img>` tag with the incoming frame data. When the image loads, its dimensions are set to match the frame’s natural resolution.
- **Usage:**
  - Host this file on a web server (or on Glitch as a frontend).
  - Open the page, enter the WebSocket URL (e.g. `wss://your-signaling-server`) and the authentication password.
  - Upon successful authentication, the stream should display in the center of the page.

---

## Setup and Deployment

1. **Stream Forwarder:**
   - Ensure you have Python installed.
   - Run the script (`stream_forwarder.py`). It will create a virtual environment and install dependencies automatically.
   - Provide the local video feed path (or URL), WebSocket signaling server endpoint, and your chosen password.
   - The script will auto‑generate a `.env` file with placeholder values for future reference.

2. **Signaling Server:**
   - Ensure Node.js is installed.
   - Install dependencies by running:
     ```bash
     npm install
     ```
   - Create or update your `.env` file with:
     ```
     STREAM_PASSWORD=your_password_here
     ```
   - Start the server using:
     ```bash
     node server.js
     ```
   - Deploy on Glitch or your preferred Node.js host.

3. **Viewer Frontend:**
   - Place the `index.html` file on your web server.
   - Open it in a browser.
   - Enter the signaling server URL and password as prompted. The stream should then display in the `<img>` tag.

---

## Troubleshooting

- **Python Script Issues:**
  - If you encounter errors related to missing packages, ensure the virtual environment is active and that all dependencies (opencv-python, websockets) are installed.
  - Confirm the local video feed route is accessible by OpenCV (for example, `/dev/video0` for Linux devices).

- **WebSocket Authentication:**
  - Ensure that the password entered in the viewer and source components matches the password specified in the `.env` file used by the signaling server.

- **Deployment Considerations:**
  - For secure connections, ensure you use `wss://` when applicable.
  - Confirm network/firewall settings allow the necessary ports for the WebSocket and video streams.
