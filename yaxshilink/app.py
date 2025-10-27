from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import aiohttp
import serial_asyncio
import websockets

from .config import Config, load_config


# ------------------ GLOBAL STATE ------------------
session_active: bool = False
session_id: Optional[int] = None
serial_writer = None
loggers: dict[str, logging.Logger] = {}
cfg: Config


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
            print(f"Connected to {label} on {url}")
            return (reader, writer) if not read_only else (reader, None)
        except Exception as e:
            print(f"{label} connect failed ({url}): {e}. Retrying in 2s…")
            await asyncio.sleep(2)


async def init_arduino():
    reader, writer = await init_serial_with_retry(cfg.arduino_port, cfg.baudrate, "Arduino")
    return reader, writer


async def init_scanner():
    reader, _ = await init_serial_with_retry(cfg.scanner_port, cfg.baudrate, "Scanner", read_only=True)
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

            print(f"<- Arduino: {msg}")
            if msg == "E" and session_active:
                session_active = False
                print("Session ended by Arduino.")
                logger.info("Arduino ended session.")
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            await asyncio.sleep(1)


# ------------------ SCANNER HANDLER ------------------
async def scanner_listener(scanner_reader):
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
                    print(f"Scanner read: {line}")
                    await send_sku_to_api(line)
        except Exception as e:
            print(f"Scanner error: {e}")
            await asyncio.sleep(0.1)


# ------------------ API HANDLERS ------------------
async def send_sku_to_api(sku: str):
    global session_id
    logger = get_logger(session_id)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(cfg.api_check_url, json={"sku": sku}) as resp:
                data = await resp.json()

            if not data.get("exists"):
                msg = f"{sku} → Not found"
                print(msg)
                logger.warning(msg)
                await send_to_arduino("R")
                return

            bottle = data.get("bottle", {})
            material = bottle.get("material")
            name = bottle.get("name", "Unknown")

            msg = f"{sku} → {name} ({material})"
            print(msg)
            logger.info(msg)

            await send_to_arduino(material if material in ("P", "A") else "R")

            if session_id:
                post_url = cfg.session_item_url(session_id)
                async with session.post(post_url, json={"sku": sku}) as post_resp:
                    if post_resp.status in (200, 201):
                        print(f"{sku} added to session.")
                        logger.info(f"{sku} added to session.")
                    else:
                        err = await post_resp.text()
                        logger.error(f"Failed to send to session: {post_resp.status} → {err}")
        except Exception as e:
            logger.exception(f"API error: {e}")


# ------------------ WEBSOCKET HANDLER ------------------
async def websocket_listener():
    global session_active, session_id
    sys_logger = get_logger()

    print(f"WebSocket: {cfg.ws_url}")
    try:
        async with websockets.connect(cfg.ws_url) as ws:
            print("WebSocket connected. Waiting for messages…")
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
                    print(f"Session #{session_id} {state}.")
                    logger.info(f"Session #{session_id} {state}.")
                    await send_to_arduino("S" if active else "E")

                elif event == "session_stopped" and payload.get("session_id") == session_id:
                    session_active = False
                    print(f"Session #{session_id} stopped.")
                    sys_logger.info(f"Session #{session_id} stopped.")
                    await send_to_arduino("E")

    except Exception as e:
        sys_logger.error(f"WebSocket error: {e}")
        print("WebSocket connection lost. Retrying in 3s…")
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
        scanner_listener(scanner_reader),
    )


def run(config_path: Optional[str] = None):
    global cfg, LOG_DIR
    cfg = load_config(Path(config_path) if config_path else None)
    LOG_DIR = choose_log_dir(cfg.log_dir)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program stopped.")


if __name__ == "__main__":
    run()
