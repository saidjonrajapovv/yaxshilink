import asyncio
import json
import aiohttp
import serial_asyncio
import websockets
import logging
from pathlib import Path

# ------------------ CONFIG ------------------
BASE_IP = "10.10.3.49:8000"
DEVICE_NUMBER = "0f00b3d8-f6e2-4e0d-8a7b-61e0838c8f6f"

API_CHECK_URL = f"http://{BASE_IP}/api/bottle/check/"
SESSION_ITEM_URL = f"http://{BASE_IP}/api/session/{{session_id}}/items/"
WS_URL = f"ws://{BASE_IP}/ws/device/{DEVICE_NUMBER}/"

ARDUINO_PORT = "/dev/ttyUSB0"
SCANNER_PORT = "/dev/ttyACM0"
BAUDRATE = 9600

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ------------------ STATE ------------------
session_active = False
session_id = None
serial_writer = None
loggers = {}

# ------------------ LOGGING ------------------
def get_logger(session_id: int = None) -> logging.Logger:
    """Create or get a logger instance for system or session."""
    name = f"session_{session_id}" if session_id else "system"
    log_file = LOG_DIR / f"{name}.log"

    if name not in loggers:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
        logger.addHandler(handler)
        loggers[name] = logger

    return loggers[name]

# ------------------ SERIAL CONNECTIONS ------------------
async def init_arduino():
    """Initialize Arduino serial connection."""
    reader, writer = await serial_asyncio.open_serial_connection(url=ARDUINO_PORT, baudrate=BAUDRATE)
    print(f"🔌 Connected to Arduino on {ARDUINO_PORT}")
    return reader, writer

async def init_scanner():
    """Initialize Scanner serial connection."""
    reader, _ = await serial_asyncio.open_serial_connection(url=SCANNER_PORT, baudrate=BAUDRATE)
    print(f"📡 Connected to Scanner on {SCANNER_PORT}")
    print("📸 Scanner active — waiting for barcodes...")
    return reader

# ------------------ ARDUINO HANDLERS ------------------
async def send_to_arduino(cmd: str):
    """Send a command to Arduino."""
    if not serial_writer:
        print("⚠️ Arduino not connected")
        return

    try:
        serial_writer.write(f"{cmd}\n".encode())
        await serial_writer.drain()
        print(f"⬆️ Sent to Arduino: {cmd}")
    except Exception as e:
        print(f"❌ Arduino write error: {e}")

async def serial_listener(reader):
    """Listen for messages from Arduino."""
    global session_active
    logger = get_logger()

    while True:
        try:
            line = await reader.readline()
            msg = line.decode(errors="ignore").strip()
            if not msg:
                continue

            print(f"⬇️ Arduino says: {msg}")
            if msg == "E" and session_active:
                session_active = False
                print("🛑 Session ended by Arduino.")
                logger.info("Arduino ended session.")
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            await asyncio.sleep(1)

# ------------------ SCANNER HANDLER ------------------
async def scanner_listener(scanner_reader):
    """Read barcodes from scanner, process and send to API."""
    print(f"\n📡 Listening for scanner data on {SCANNER_PORT}")
    buffer = bytearray()

    while True:
        try:
            chunk = await scanner_reader.read(128)
            if not chunk:
                await asyncio.sleep(0.01)
                continue

            buffer.extend(chunk)
            # Split on newline or carriage return
            while (idx := next((i for i, b in enumerate(buffer) if b in (10, 13)), -1)) != -1:
                line = buffer[:idx].decode(errors="ignore").strip()
                del buffer[: idx + 1]
                if buffer[:1] in (b"\n", b"\r"):
                    del buffer[:1]
                if line:
                    print(f"🔍 Scanner read: {line}")
                    if session_active:
                        await send_sku_to_api(line)
        except Exception as e:
            print(f"❌ Scanner error: {e}")
            await asyncio.sleep(0.1)

# ------------------ API HANDLERS ------------------
async def send_sku_to_api(sku: str):
    """Validate SKU with API and forward to Arduino + backend session."""
    global session_id
    logger = get_logger(session_id)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_CHECK_URL, json={"sku": sku}) as resp:
                data = await resp.json()

            if not data.get("exists"):
                msg = f"🚫 {sku} → Not found"
                print(msg)
                logger.warning(msg)
                await send_to_arduino("R")
                return

            bottle = data.get("bottle", {})
            material = bottle.get("material")
            name = bottle.get("name", "Unknown")

            msg = f"✅ {sku} → {name} ({material})"
            print(msg)
            logger.info(msg)

            # Send command to Arduino
            await send_to_arduino(material if material in ("P", "A") else "R")

            # Add to active session
            if session_id:
                post_url = SESSION_ITEM_URL.format(session_id=session_id)
                async with session.post(post_url, json={"sku": sku}) as post_resp:
                    if post_resp.status in (200, 201):
                        print(f"📦 {sku} added to session.")
                        logger.info(f"{sku} added to session.")
                    else:
                        err = await post_resp.text()
                        logger.error(f"⚠️ Failed to send to session: {post_resp.status} → {err}")
        except Exception as e:
            logger.exception(f"API error: {e}")

# ------------------ WEBSOCKET HANDLER ------------------
async def websocket_listener():
    """Handle WebSocket events for session management."""
    global session_active, session_id
    sys_logger = get_logger()

    print(f"\n🔗 WebSocket: {WS_URL}")
    try:
        async with websockets.connect(WS_URL) as ws:
            print("✅ WebSocket connected. Waiting for messages...\n")
            sys_logger.info("WebSocket connected.")

            async for msg in ws:
                data = json.loads(msg)
                event = data.get("event")
                payload = data.get("data", {})

                if event == "session_created":
                    session_id = payload.get("session_id")
                    active = payload.get("status") == "active"
                    logger = get_logger(session_id)
                    session_active = active

                    state = "started" if active else "blocked"
                    print(f"\n🟢 Session #{session_id} {state}.")
                    logger.info(f"Session #{session_id} {state}.")
                    await send_to_arduino("S" if active else "E")

                elif event == "session_stopped" and payload.get("session_id") == session_id:
                    session_active = False
                    print(f"\n🛑 Session #{session_id} stopped.")
                    sys_logger.info(f"Session #{session_id} stopped.")
                    await send_to_arduino("E")

    except Exception as e:
        sys_logger.error(f"WebSocket error: {e}")
        print("❌ WebSocket connection lost. Retrying in 3s...")
        await asyncio.sleep(3)
        asyncio.create_task(websocket_listener())

# ------------------ MAIN ------------------
async def main():
    global serial_writer
    arduino_reader, serial_writer = await init_arduino()
    scanner_reader = await init_scanner()

    await asyncio.gather(
        websocket_listener(),
        serial_listener(arduino_reader),
        scanner_listener(scanner_reader)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Program stopped.")
