import asyncio
import websockets
import json
import aiohttp
import logging
import pyperclip
import serial_asyncio
from datetime import datetime
from pathlib import Path

DEVICE_ID = "ec575e49-e579-4e1c-a819-33c242919aae"
BASE_URL = "http://127.0.0.1:8000/api/"

API_CHECK_URL = BASE_URL + "bottle/check/"
SESSION_ITEM_URL = BASE_URL + "session/{session_id}/items/"
WS_URL = "ws://127.0.0.1:8000/ws/device/" + DEVICE_ID + "/"
SERIAL_PORT = "/dev/ttyACM0"
# SERIAL_PORT = "/dev/tty.usbmodemXXXX"
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


class SerialHandler(asyncio.Protocol):
    def connection_made(self, transport):
        global serial_writer
        serial_writer = transport
        print(f"🔌 Connected to Arduino on {SERIAL_PORT}")
        get_logger().info("Connected to Arduino.")

    def data_received(self, data):
        global session_active
        text = data.decode("utf-8", errors="ignore").strip()
        for ch in text:
            if ch == "E":
                print("🛑 Arduino sent 'E' (end signal).")
                if session_active:
                    session_active = False
                    print("🔴 Session stopped (by Arduino).")
                    get_logger(session_id).info("Session stopped by Arduino.")
            else:
                print(f"🔹 Arduino → {ch}")

    def connection_lost(self, exc):
        print("❌ Serial connection lost.")
        get_logger().error("Serial connection lost.")


async def send_serial(cmd: str):
    """Send a single-character command to Arduino."""
    global serial_writer
    if serial_writer:
        serial_writer.write((cmd + "\n").encode("utf-8"))
        print(f"➡️ Sent to Arduino: '{cmd}'")
    else:
        print("⚠️ Serial not ready — cannot send command.")


async def send_sku_to_api(sku: str):
    global session_id
    logger = get_logger(session_id)

    async with aiohttp.ClientSession() as session:
        try:
            payload = {"sku": sku}
            async with session.post(API_CHECK_URL, json=payload) as response:
                data = await response.json()

                if data.get("exists") is False:
                    msg = f"🚫 {sku} → Not found (Material: {data.get('material')})"
                    print(msg)
                    logger.warning(msg)
                    await send_serial("R")
                    return

                if data.get("exists") is True:
                    bottle = data.get("bottle", {})
                    material = bottle.get("material")
                    msg = f"✅ {sku} → {bottle.get('name')} ({material})"
                    print(msg)
                    logger.info(msg)

                    if material == "P":
                        await send_serial("P")
                    elif material == "A":
                        await send_serial("A")

                    if session_id:
                        post_url = SESSION_ITEM_URL.format(session_id=session_id)
                        async with session.post(post_url, json={"sku": sku}) as post_resp:
                            if post_resp.status in (200, 201):
                                success_msg = f"📦 {sku} added to session."
                                print(success_msg)
                                logger.info(success_msg)
                            else:
                                err = await post_resp.text()
                                fail_msg = f"⚠️ Session post failed: {post_resp.status} → {err}"
                                logger.error(fail_msg)
                    else:
                        logger.warning(f"No session ID — SKU '{sku}' not sent.")

        except Exception as e:
            logger.exception(f"Unexpected error: {e}")


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
                        await send_serial("S")
                        session_logger.info(f"Session #{session_id} started.")
                    else:
                        session_active = False
                        print(f"\n🔴 Session #{session_id} inactive.")
                        session_logger.info(f"Session #{session_id} inactive.")

                elif event == "session_stopped":
                    stopped_id = data.get("session_id")
                    if stopped_id == session_id:
                        session_active = False
                        await send_serial("E")
                        session_logger = get_logger(session_id)
                        print(f"\n🛑 Session #{stopped_id} stopped.")
                        session_logger.info(f"Session #{stopped_id} stopped.")

    except Exception as e:
        system_logger.error(f"WebSocket error: {e}")
        print("❌ WebSocket connection lost.")


async def clipboard_listener():
    global session_active
    logger = get_logger()
    last_text = ""
    last_time = datetime.now()
    logger.info("Clipboard listener started.")
    print("\n📋 Clipboard listener active.\n")

    while True:
        try:
            text = pyperclip.paste().strip()
            if text:
                now = datetime.now()
                if text != last_text or (now - last_time).total_seconds() > 0.1:
                    last_text = text
                    last_time = now

                    if session_active:
                        print(f"📥 {text}")
                        await send_sku_to_api(text)
                    else:
                        logger.warning(f"Session inactive — '{text}' not sent.")

                    pyperclip.copy('')

        except Exception as e:
            logger.error(f"Clipboard error: {e}")

        await asyncio.sleep(0.1)


async def main():
    loop = asyncio.get_running_loop()

    transport, protocol = await serial_asyncio.create_serial_connection(
        asyncio.get_running_loop,
        lambda: SerialHandler(),
        SERIAL_PORT,
        BAUDRATE
    )

    listener_task = asyncio.create_task(websocket_listener())
    clipboard_task = asyncio.create_task(clipboard_listener())
    await asyncio.gather(listener_task, clipboard_task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Program stopped.")
