from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


async def init_scanner(port: str, baudrate: int):
    """Initialize Scanner serial connection."""
    import serial_asyncio

    reader, _ = await serial_asyncio.open_serial_connection(url=port, baudrate=baudrate)
    print(f"📡 Connected to Scanner on {port}")
    print("📸 Scanner active — waiting for barcodes...")
    return reader


async def scanner_listener(
    read_stream,
    is_session_active: Callable[[], bool],
    on_barcode: Callable[[str], Awaitable[None]],
    log_info: Callable[[str], None],
):
    """Read barcodes from scanner, process and send to API."""
    buffer = bytearray()

    while True:
        try:
            chunk = await read_stream.read(128)
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
                    # Persist to system log as well
                    try:
                        log_info(f"Scanner read: {line}")
                    except Exception:
                        pass
                    if is_session_active():
                        await on_barcode(line)
        except Exception as e:
            print(f"❌ Scanner error: {e}")
            await asyncio.sleep(0.1)
