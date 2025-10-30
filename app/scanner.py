from __future__ import annotations

import asyncio
import os
import time
from typing import Awaitable, Callable


async def init_scanner(port: str, baudrate: int):
    """Initialize Scanner serial connection."""
    import serial_asyncio
    import serial  # type: ignore

    # Be explicit about serial params to avoid flow-control/parity mismatches
    reader, _ = await serial_asyncio.open_serial_connection(
        url=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )
    print(f"📡 Connected to Scanner on {port}")
    print("📸 Scanner active — waiting for barcodes...")
    return reader


async def scanner_listener(
    read_stream,
    is_session_active: Callable[[], bool],
    on_barcode: Callable[[str], Awaitable[None]],
    log_info: Callable[[str], None],
    flush_timeout_ms: int = 150,
    max_line_len: int = 512,
    raw_debug: bool | None = None,
):
    """Read barcodes from scanner, process and send to API."""
    buffer = bytearray()
    last_rx = time.monotonic()
    if raw_debug is None:
        raw_debug = os.environ.get("YL_DEBUG_SCANNER", "").lower() in ("1", "true", "yes")

    while True:
        try:
            chunk = await read_stream.read(128)
            if chunk:
                # Log every chunk (raw bytes) to system log
                try:
                    hexp = " ".join(f"{b:02X}" for b in chunk)
                    asc = chunk.decode(errors="ignore").replace("\r", "\\r").replace("\n", "\\n")
                    log_info(f"Scanner raw: HEX: {hexp} | ASCII: {asc}")
                except Exception:
                    pass
                last_rx = time.monotonic()
                buffer.extend(chunk)
                if len(buffer) > max_line_len:
                    # Avoid unbounded growth if terminator missing
                    line = buffer.decode(errors="ignore").strip()
                    buffer.clear()
                    if line:
                        print(f"🔍 Scanner (maxlen flush): {line}")
                        try:
                            log_info(f"Scanner read: {line}")
                        except Exception:
                            pass
                        if is_session_active():
                            await on_barcode(line)
                    continue
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
            else:
                # If idle and buffer has data but no terminator, flush as line
                if buffer and (time.monotonic() - last_rx) * 1000 >= flush_timeout_ms:
                    line = buffer.decode(errors="ignore").strip()
                    buffer.clear()
                    if line:
                        print(f"🔍 Scanner (timeout flush): {line}")
                        try:
                            log_info(f"Scanner read: {line}")
                        except Exception:
                            pass
                        if is_session_active():
                            await on_barcode(line)
                await asyncio.sleep(0.01)
                continue
        except Exception as e:
            print(f"❌ Scanner error: {e}")
            await asyncio.sleep(0.1)
