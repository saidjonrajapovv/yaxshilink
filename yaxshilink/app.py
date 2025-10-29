from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Any

import serial_asyncio
import websockets

from .config import Config, load_config
from .ui import TerminalUI


# ------------------ GLOBAL STATE ------------------
session_active: bool = False
session_id: Optional[str] = None
serial_writer = None
loggers: dict[str, logging.Logger] = {}
cfg: Config
ui: TerminalUI
ws = None
ws_send_lock: asyncio.Lock
pending_check_future: Optional[asyncio.Future] = None
last_activity: float = 0.0


def choose_log_dir(custom: Optional[str]) -> Path:
    candidates = []
    if custom:
        candidates.append(Path(custom))
    candidates.extend(
        [
            Path("/var/log/yaxshilink"),
            Path.home() / ".local/state/yaxshilink/logs",
            Path.cwd() / "logs",
        ]
    )
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            # test write
            (d / ".write_test").write_text("ok", encoding="utf-8")
            (d / ".write_test").unlink(missing_ok=True)
            return d
        except Exception:
            continue
    # fallback
    d = Path.cwd() / "logs"
    d.mkdir(exist_ok=True)
    return d


LOG_DIR: Path


def get_logger(session: Optional[int] = None) -> logging.Logger:
    name = f"session_{session}" if session else "system"
    if name in loggers:
        return loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
    logger.addHandler(handler)
    loggers[name] = logger
    return logger


# ------------------ SERIAL CONNECTIONS ------------------
async def init_serial_with_retry(url: str, baudrate: int, label: str, read_only: bool = False):
    while True:
        try:
            reader, writer = await serial_asyncio.open_serial_connection(url=url, baudrate=baudrate)
            if not cfg.quiet_terminal:
                print(f"Connected to {label} on {url}")
            return (reader, writer) if not read_only else (reader, None)
        except Exception as e:
            if not cfg.quiet_terminal:
                print(f"{label} connect failed ({url}): {e}. Retrying in 2s…")
            await asyncio.sleep(2)


async def init_arduino():
    reader, writer = await init_serial_with_retry(cfg.arduino_port, cfg.baudrate, "Arduino")
    return reader, writer


async def init_scanner():
    reader, _ = await init_serial_with_retry(cfg.scanner_port, cfg.baudrate, "Scanner", read_only=True)
    if not cfg.quiet_terminal:
        print("Scanner active — waiting for barcodes…")
    return reader


# ------------------ ARDUINO HANDLERS ------------------
async def send_to_arduino(cmd: str):
    if not serial_writer:
        print("Arduino not connected")
        return
    try:
        serial_writer.write(f"{cmd}\n".encode())
        await serial_writer.drain()
        if not cfg.quiet_terminal:
            print(f"-> Arduino: {cmd}")
    except Exception as e:
        print(f"Arduino write error: {e}")


async def serial_listener(reader):
    global session_active
    logger = get_logger()

    while True:
        try:
            line = await reader.readline()
            msg = line.decode(errors="ignore").strip()
            if not msg:
                continue

            if not cfg.quiet_terminal:
                print(f"<- Arduino: {msg}")
            if msg == "E" and session_active:
                session_active = False
                if not cfg.quiet_terminal:
                    print("Session ended by Arduino.")
                logger.info("Arduino ended session.")
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            await asyncio.sleep(1)


# ------------------ SCANNER HANDLER ------------------
async def scanner_listener(scanner_reader):
    if not cfg.quiet_terminal:
        print(f"Listening for scanner data on {cfg.scanner_port}")
    buffer = bytearray()

    while True:
        try:
            chunk = await scanner_reader.read(128)
            if not chunk:
                await asyncio.sleep(0.01)
                continue

            buffer.extend(chunk)
            while (idx := next((i for i, b in enumerate(buffer) if b in (10, 13)), -1)) != -1:
                line = buffer[:idx].decode(errors="ignore").strip()
                del buffer[: idx + 1]
                if buffer[:1] in (b"\n", b"\r"):
                    del buffer[:1]
                if line and session_active:
                    if not cfg.quiet_terminal:
                        print(f"Scanner read: {line}")
                    await process_barcode(line)
        except Exception as e:
            print(f"Scanner error: {e}")
            await asyncio.sleep(0.1)


# ------------------ WS MESSAGE HELPERS ------------------
async def ws_send(msg: dict[str, Any]):
    global ws
    async with ws_send_lock:
        await ws.send(json.dumps(msg))


def map_material_to_arduino(material: str) -> str:
    m = (material or "").lower()
    if m.startswith("plast"):
        return "P"
    if m.startswith("alum"):
        return "A"
    return "R"


def now_utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def next_bottle_code() -> str:
    counter_file = LOG_DIR / f"counter_{cfg.fandomat_id}.txt"
    try:
        n = int(counter_file.read_text().strip())
    except Exception:
        n = 0
    n += 1
    try:
        counter_file.write_text(str(n))
    except Exception:
        pass
    return f"BTL-{cfg.fandomat_id:03d}-{n:05d}"


async def process_barcode(sku: str):
    global pending_check_future, last_activity
    logger = get_logger(session_id)

    async def _check_and_wait():
        nonlocal sku
        # Send CHECK_BOTTLE
        await ws_send({
            "type": "CHECK_BOTTLE",
            "session_id": session_id,
            "sku": sku,
        })
        # Wait for BOTTLE_CHECK_RESULT
        fut = asyncio.get_event_loop().create_future()
        pending_check_future = fut
        try:
            res = await asyncio.wait_for(fut, timeout=10)
            return res
        finally:
            pending_check_future = None

    try:
        data = await ui.run_with_progress(
            title="WS CHECK_BOTTLE",
            coro=_check_and_wait(),
            update_hint=f"SKU: {sku}",
        )
    except asyncio.TimeoutError:
        ui.show_special("ERROR")
        logger.error("CHECK_BOTTLE timeout")
        return

    exist = data.get("exist") or data.get("exists")
    if not exist:
        ui.show_special("NOT_FOUND")
        logger.warning(f"{sku} not found")
        await send_to_arduino("R")
        return

    bottle = data.get("bottle", {})
    material = bottle.get("material", "")
    await send_to_arduino(map_material_to_arduino(material))
    ui.show_special("FOUND")
    logger.info(f"{sku} accepted ({material})")

    # Send BOTTLE_ACCEPTED
    code = next_bottle_code()
    await ws_send({
        "type": "BOTTLE_ACCEPTED",
        "session_id": session_id,
        "code": code,
        "material": material,
        "timestamp": now_utc_iso(),
    })
    last_activity = asyncio.get_event_loop().time()


# ------------------ WEBSOCKET HANDLER ------------------
async def websocket_listener():
    global session_active, session_id, ws, pending_check_future, last_activity
    sys_logger = get_logger()
    if not cfg.quiet_terminal:
        print(f"WebSocket: {cfg.ws_url}")
    try:
        async with websockets.connect(cfg.ws_url) as _ws:
            ws = _ws
            if not cfg.quiet_terminal:
                print("WebSocket connected. Waiting for messages…")
            sys_logger.info("WebSocket connected.")

            # Send HELLO
            await ws_send({
                "type": "HELLO",
                "fandomat_id": cfg.fandomat_id,
                "device_token": cfg.device_token,
                "version": cfg.version,
            })

            # Read loop
            async for msg in ws:
                data = json.loads(msg)
                mtype = data.get("type")

                if mtype == "OK":
                    ui.show_special("HELLO_OK")
                    sys_logger.info(data.get("message", "OK"))

                elif mtype == "ERROR":
                    ui.show_special("HELLO_ERROR")
                    sys_logger.error(data.get("error", "ERROR"))

                elif mtype == "PING":
                    await ws_send({"type": "PONG"})

                elif mtype == "START_SESSION":
                    session_id = data.get("session_id")
                    session_active = True
                    last_activity = asyncio.get_event_loop().time()
                    ui.show_special("SESSION_STARTED")
                    sys_logger.info(f"Session {session_id} started")
                    await send_to_arduino("S")
                    # acknowledge
                    await ws_send({"type": "SESSION_STARTED", "session_id": session_id})

                elif mtype == "CANCEL_SESSION":
                    if data.get("session_id") == session_id:
                        session_active = False
                        ui.show_special("SESSION_STOPPED")
                        sys_logger.info(f"Session {session_id} cancelled")
                        await send_to_arduino("E")

                elif mtype == "BOTTLE_CHECK_RESULT":
                    fut = pending_check_future
                    if fut and not fut.done():
                        fut.set_result(data)

    except Exception as e:
        sys_logger.error(f"WebSocket error: {e}")
        if not cfg.quiet_terminal:
            print("WebSocket connection lost. Retrying in 3s…")
        await asyncio.sleep(3)
        asyncio.create_task(websocket_listener())


async def inactivity_watcher(timeout_seconds: int = 90):
    global session_active, last_activity, session_id
    logger = get_logger()
    loop = asyncio.get_event_loop()
    while True:
        try:
            if session_active:
                now = loop.time()
                if now - last_activity >= timeout_seconds:
                    # send SESSION_END
                    sid = session_id
                    await ws_send({"type": "SESSION_END", "session_id": sid})
                    session_active = False
                    ui.show_special("SESSION_STOPPED")
                    logger.info(f"Session {sid} ended by inactivity")
                    await send_to_arduino("E")
            await asyncio.sleep(1)
        except Exception:
            await asyncio.sleep(1)


# ------------------ MAIN ------------------
async def main():
    global serial_writer, ws_send_lock
    arduino_reader, serial_writer = await init_arduino()
    scanner_reader = await init_scanner()
    ws_send_lock = asyncio.Lock()

    await asyncio.gather(
        websocket_listener(),
        serial_listener(arduino_reader),
        scanner_listener(scanner_reader),
        inactivity_watcher(),
    )


def run(config_path: Optional[str] = None):
    global cfg, LOG_DIR
    cfg = load_config(Path(config_path) if config_path else None)

    print(cfg.base_url)
    LOG_DIR = choose_log_dir(cfg.log_dir)
    global ui
    ui = TerminalUI(enabled=True)  # We still show minimal UI, regardless of quiet prints
    # Show header: device and endpoints
    ui.set_header([
        f"DEVICE_TOKEN: {cfg.device_token}",
        f"FANDOMAT_ID: {cfg.fandomat_id}",
        f"WS: {cfg.ws_url}",
    ])
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if not cfg.quiet_terminal:
            print("Program stopped.")


if __name__ == "__main__":
    run()
