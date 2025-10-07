import asyncio
import json
import aiohttp
import serial_asyncio
import websockets
import logging
from pathlib import Path

BASE_IP = "10.10.3.49:8000"
DEVICE_NUMBER = "0f00b3d8-f6e2-4e0d-8a7b-61e0838c8f6f"

API_CHECK_URL = f"http://{BASE_IP}/api/bottle/check/"
SESSION_ITEM_URL = f"http://{BASE_IP}/api/session/{{session_id}}/items/"
WS_URL = f"ws://{BASE_IP}/ws/device/{DEVICE_NUMBER}/"

ARDUINO_PORT = "/dev/ttyUSB0"
SCANNER_PORT = "/dev/ttyACM0"
BAUDRATE = 9600

session_active = False
session_id = None
serial_writer = None
loggers = {}

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def get_logger(session_id: int = None) -> logging.Logger:
    """Create dedicated logger for session."""
    global loggers
    if not session_id:
        name = "system"
        log_file = LOG_DIR / "system.log"
    else:
        name = f"session_{session_id}"
        log_file = LOG_DIR / f"session_{session_id}.log"

    if name in loggers:
        return loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
    logger.addHandler(fh)
    loggers[name] = logger
    return logger


async def init_serial_ports():
    """Connect to Arduino and Scanner."""
    global serial_writer

    # Arduino
    arduino_reader, arduino_writer = await serial_asyncio.open_serial_connection(
        url=ARDUINO_PORT, baudrate=BAUDRATE
    )
    serial_writer = arduino_writer
    print(f"🔌 Arduino connected on {ARDUINO_PORT}")

    # Scanner
    scanner_reader, _ = await serial_asyncio.open_serial_connection(
        url=SCANNER_PORT, baudrate=BAUDRATE
    )
    print(f"📠 Scanner connected on {SCANNER_PORT}")

    return arduino_reader, scanner_reader


async def send_to_arduino(cmd: str):
    """Send single-character command to Arduino."""
    global serial_writer
    if serial_writer:
        serial_writer.write((cmd + "\n").encode("utf-8"))
        await serial_writer.drain()
        print(f"⬆️ Sent to Arduino: {cmd}")
    else:
        print("⚠️ Arduino not connected")


async def send_sku_to_api(sku: str):
    """Check SKU validity and forward to session."""
    global session_id
    logger = get_logger(session_id)

    async with aiohttp.ClientSession() as session:
        try:
            payload = {"sku": sku}
            async with session.post(API_CHECK_URL, json=payload) as response:
                data = await response.json()

                if data.get("exists") is False:
                    msg = f"🚫 {sku} → Not found"
                    print(msg)
                    logger.warning(msg)
                    await send_to_arduino("R")
                    return

                bottle = data.get("bottle", {})
                material = bottle.get("material")
                msg = f"✅ {sku} → {bottle.get('name')} ({material})"
                print(msg)
                logger.info(msg)

                if material == "P":
                    await send_to_arduino("P")
                elif material == "A":
                    await send_to_arduino("A")
                else:
                    await send_to_arduino("R")

                if session_id:
                    post_url = SESSION_ITEM_URL.format(session_id=session_id)
                    async with session.post(post_url, json={"sku": sku}) as post_resp:
                        if post_resp.status in (200, 201):
                            success_msg = f"📦 {sku} added to session."
                            print(success_msg)
                            logger.info(success_msg)
                        else:
                            err = await post_resp.text()
                            fail_msg = f"⚠️ Session add failed: {post_resp.status} → {err}"
                            logger.error(fail_msg)
                else:
                    logger.warning(f"No session ID — SKU '{sku}' not sent.")

        except Exception as e:
            logger.exception(f"Unexpected error: {e}")


async def websocket_listener():
    """Listen to backend WebSocket for session events."""
    global session_active, session_id
    system_logger = get_logger()
    print(f"\n🔗 Connecting WebSocket: {WS_URL}")

    try:
        async with websockets.connect(WS_URL) as websocket:
            print("✅ WebSocket connected. Waiting for events...\n")
            system_logger.info("WebSocket connected.")

            while True:
                message = await websocket.recv()
                msg = json.loads(message)
                event = msg.get("event")
                data = msg.get("data", {})

                if event == "session_created":
                    session_id = data.get("session_id")
                    status = data.get("status")
                    session_logger = get_logger(session_id)

                    if status == "active":
                        session_active = True
                        print(f"\n🟢 Session #{session_id} started.")
                        session_logger.info(f"Session #{session_id} started.")
                        await send_to_arduino("S")
                    else:
                        session_active = False
                        print(f"\n🔴 Session #{session_id} blocked.")
                        await send_to_arduino("E")

                elif event == "session_stopped":
                    stopped_id = data.get("session_id")
                    if stopped_id == session_id:
                        session_active = False
                        print(f"\n🛑 Session #{stopped_id} stopped.")
                        await send_to_arduino("E")

    except Exception as e:
        system_logger.error(f"WebSocket error: {e}")
        print("❌ WebSocket connection lost. Retrying in 5s...")
        await asyncio.sleep(5)
        asyncio.create_task(websocket_listener())


async def arduino_listener(arduino_reader):
    """Listen to Arduino messages (like button press)."""
    global session_active
    logger = get_logger()

    while True:
        try:
            line = await arduino_reader.readline()
            if not line:
                continue
            msg = line.decode(errors="ignore").strip()
            if not msg:
                continue

            print(f"⬇️ Arduino says: {msg}")
            if msg == "E" and session_active:
                logger.info("Arduino → E (button pressed)")
                session_active = False
                print("🛑 Session ended by Arduino (button).")

        except Exception as e:
            logger.error(f"Serial read error: {e}")
            await asyncio.sleep(1)


# ------------------ SCANNER LISTENER ------------------
async def scanner_listener(scanner_reader):
    """Listen directly to Netum scanner input (always print scanned data)."""
    global session_active
    logger = get_logger()

    print("\n📡 Scanner active — waiting for scans...\n")

    while True:
        try:
            line = await scanner_reader.readline()
            if not line:
                continue

            sku = line.decode(errors="ignore").strip()
            if not sku:
                continue

            # Always show scanned data on terminal
            print(f"🧾 Scanned: {sku}")
            logger.info(f"Scanned: {sku}")

            # Send to API only if session active
            if session_active:
                await send_sku_to_api(sku)
            else:
                print("⚠️ No active session — scan not sent to server.")
                logger.warning(f"Scan ignored (inactive session): {sku}")

        except Exception as e:
            logger.error(f"Scanner read error: {e}")
            await asyncio.sleep(1)


async def main():
    arduino_reader, scanner_reader = await init_serial_ports()

    await asyncio.gather(
        websocket_listener(),
        arduino_listener(arduino_reader),
        scanner_listener(scanner_reader),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Program stopped by user.")
