from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import serial_asyncio

from .state import AppState


async def init_arduino(port: str, baudrate: int):
    """Initialize Arduino serial connection."""
    reader, writer = await serial_asyncio.open_serial_connection(
        url=port, baudrate=baudrate
    )
    print(f"🔌 Connected to Arduino on {port}")
    return reader, writer


async def send_to_arduino(state: AppState, cmd: str):
    """Send a command to Arduino."""
    writer = state.serial_writer
    if not writer:
        print("⚠️ Arduino not connected")
        return

    try:
        writer.write(f"{cmd}\n".encode())
        await writer.drain()
        print(f"⬆️ Sent to Arduino: {cmd}")
    except Exception as e:
        print(f"❌ Arduino write error: {e}")


async def serial_listener(
    state: AppState,
    reader: asyncio.StreamReader,
    log_info: Callable[[str], None],
    log_error: Callable[[str], None],
):
    """Listen for messages from Arduino."""
    while True:
        try:
            line = await reader.readline()
            msg = line.decode(errors="ignore").strip()
            if not msg:
                continue

            print(f"⬇️ Arduino says: {msg}")
            if msg == "E" and state.session_active:
                state.session_active = False
                print("🛑 Session ended by Arduino.")
                log_info("Arduino ended session.")
        except Exception as e:
            log_error(f"Serial read error: {e}")
            await asyncio.sleep(1)
