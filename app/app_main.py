from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, Callable, Awaitable

from .config import load_config
from .logger import get_logger as _get_logger
from .state import AppState
from .arduino import init_arduino, send_to_arduino, serial_listener
from .scanner import init_scanner, scanner_listener
from .ws_client import websocket_listener


async def run():
    cfg = load_config()

    # Prepare logging
    log_dir = Path(cfg.log_dir)

    def get_logger(session_id=None):
        return _get_logger(log_dir, session_id)

    state = AppState()

    # Initialize hardware
    arduino_reader, arduino_writer = await init_arduino(cfg.arduino_port, cfg.baudrate)
    state.serial_writer = arduino_writer
    scanner_reader = await init_scanner(cfg.scanner_port, cfg.baudrate)
    # Log hardware connections to system log
    get_logger(None).info(f"Arduino connected on {cfg.arduino_port}")
    get_logger(None).info(f"Scanner connected on {cfg.scanner_port}")

    # Compose helpers bound with state
    async def send(cmd: str):
        await send_to_arduino(state, cmd)

    # This will be provided by ws_client when connected
    ws_send: Optional[Callable[[dict], Awaitable[None]]] = None

    def set_ws_sender(sender: Callable[[dict], Awaitable[None]]):
        nonlocal ws_send
        ws_send = sender

    async def arduino_task():
        logger = get_logger(None)
        await serial_listener(
            state,
            arduino_reader,
            lambda m: logger.info(m),
            lambda m: logger.error(m),
        )

    async def scanner_task():
        logger = get_logger(None)
        async def on_barcode(sku: str):
            # Send CHECK_BOTTLE over WS when session active
            if state.session_active and state.session_id and ws_send:
                await ws_send({"type": "CHECK_BOTTLE", "session_id": state.session_id, "sku": sku})
        await scanner_listener(
            scanner_reader,
            lambda: state.session_active,
            on_barcode,
            lambda m: logger.info(m),
        )

    await asyncio.gather(
        websocket_listener(state, cfg, get_logger, send, set_ws_sender),
        arduino_task(),
        scanner_task(),
    )
