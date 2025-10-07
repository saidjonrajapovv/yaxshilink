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
SESSION_ITEM_URL = "http://"+BASE_IP + "/api/session/{session_id}/items/"
WS_URL = f"ws://{BASE_IP}/ws/device/{DEVICE_NUMBER}/"

SERIAL_PORT = "/dev/ttyUSB0"
BAUDRATE = 9600

session_active = False
session_id = None
serial_writer = None
loggers = {}

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def get_logger(session_id: int = None) -> logging.Logger:
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


# ------------------ SERIAL ------------------
async def init_serial():
    """Initialize serial connection with Arduino."""
    global serial_writer
    reader, writer = await serial_asyncio.open_serial_connection(url=SERIAL_PORT, baudrate=BAUDRATE)
    serial_writer = writer
    print(f"🔌 Connected to Arduino on {SERIAL_PORT}")
    return reader, writer


async def send_to_arduino(cmd: str):
    """Send single character command to Arduino."""
    global serial_writer
    if serial_writer:
        serial_writer.write((cmd + "\n").encode("utf-8"))
        await serial_writer.drain()
        print(f"⬆️ Sent to Arduino: {cmd}")
    else:
        print("⚠️ Arduino not connected")


# ------------------ API ------------------
async def send_sku_to_api(sku: str):
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

                if data.get("exists") is True:
                    bottle = data.get("bottle", {})
                    material = bottle.get("material")
                    msg = f"✅ {sku} → {bottle.get('name')} ({material})"
                    print(msg)
                    logger.info(msg)

                    # Send to active session
                    if session_id:
                        post_url = SESSION_ITEM_URL.format(session_id=session_id)
                        async with session.post(post_url, json={"sku": sku}) as post_resp:
                            if post_resp.status in (200, 201):
                                success_msg = f"📦 {sku} added to session."
                                print(success_msg)
                                logger.info(success_msg)

                                # Send material command to Arduino
                                if material.lower() == "plastic":
                                    await send_to_arduino("P")
                                elif material.lower() == "aluminum":
                                    await send_to_arduino("A")
                                else:
                                    await send_to_arduino("R")

                            else:
                                err = await post_resp.text()
                                fail_msg = f"⚠️ Failed to send to session: {post_resp.status} → {err}"
                                logger.error(fail_msg)
                    else:
                        logger.warning(f"No session ID — SKU '{sku}' not sent.")

        except Exception as e:
            logger.exception(f"Unexpected error: {e}")


# ------------------ WEBSOCKET ------------------
async def websocket_listener():
    global session_active, session_id
    system_logger = get_logger()
    system_logger.info("WebSocket listener started.")
    print(f"\n🔗 WebSocket: {WS_URL}")

    try:
        async with websockets.connect(WS_URL) as websocket:
            print("✅ WebSocket connected. Waiting for messages...\n")
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
                        await send_to_arduino("S")  # start
                    else:
                        session_active = False
                        print(f"\n🔴 Session #{session_id} is blocked.")
                        session_logger.info(f"Session #{session_id} is blocked.")
                        await send_to_arduino("E")  # idle

                elif event == "session_stopped":
                    stopped_id = data.get("session_id")
                    if stopped_id == session_id:
                        session_active = False
                        session_logger = get_logger(session_id)
                        print(f"\n🛑 Session #{stopped_id} stopped.")
                        session_logger.info(f"Session #{stopped_id} stopped.")
                        await send_to_arduino("E")  # idle

    except Exception as e:
        system_logger.error(f"WebSocket error: {e}")
        print("❌ WebSocket connection lost.")


async def serial_listener(reader):
    """Listens to Arduino messages (e.g. 'E' for end)."""
    global session_active
    logger = get_logger()

    while True:
        try:
            line = await reader.readline()
            if not line:
                continue
            msg = line.decode(errors="ignore").strip()
            if not msg:
                continue

            print(f"⬇️ Arduino says: {msg}")
            if msg == "E":
                logger.info("Arduino → E (button pressed)")
                if session_active:
                    session_active = False
                    print("🛑 Session ended by Arduino (button).")
                    # Optionally: notify backend here via API or WS
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            await asyncio.sleep(1)


async def input_listener():
    """Handles barcode scanner or manual input."""
    global session_active
    logger = get_logger()
    print("\n⌨️ Scanner active — scan or type SKU:\n")

    loop = asyncio.get_event_loop()
    while True:
        sku = await loop.run_in_executor(None, input, "> ")
        sku = sku.strip()
        if not sku:
            continue
        if session_active:
            await send_sku_to_api(sku)
        else:
            print("⚠️ No active session — cannot send SKU.")
            logger.warning(f"Session inactive — '{sku}' ignored.")


async def main():
    reader, _ = await init_serial()
    await asyncio.gather(
        websocket_listener(),
        serial_listener(reader),
        input_listener()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Program stopped.")
