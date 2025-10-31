import asyncio
import json
import websockets
import serial_asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

# ------------------ CONFIG ------------------
WS_URL = "wss://api.yaxshi.link/ws/fandomats"
FANDOMAT_ID = 3
DEVICE_TOKEN = "fnd_a7b3c9d2e8f4g1h5i6j7k8l9m0n1"
VERSION = "1.0.0"

ARDUINO_PORT = "/dev/ttyUSB0"
SCANNER_PORT = "/dev/ttyACM0"
BAUDRATE = 9600

SESSION_TIMEOUT = 90

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


class Fandomat:
    """Encapsulates device state and all async tasks."""

    def __init__(self):
        # runtime state
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.authenticated = False
        self.current_session_id: Optional[str] = None
        self.session_active = False
        self.serial_writer = None
        self.bottle_counter = 0
        self.session_timeout_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._serial_lock = asyncio.Lock()

        # logger
        self.logger = self._get_logger()

    def _get_logger(self, name: str = "fandomat") -> logging.Logger:
        """Create/get a standard logger writing to logs/ and console."""
        logger = logging.getLogger(name)
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            fh = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
            logger.addHandler(fh)
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
            logger.addHandler(ch)
        return logger

    # ------------------ Serial I/O ------------------
    async def init_arduino(self):
        try:
            reader, writer = await serial_asyncio.open_serial_connection(url=ARDUINO_PORT, baudrate=BAUDRATE)
            self.serial_writer = writer
            self.logger.info(f"Connected to Arduino on {ARDUINO_PORT}")
            return reader
        except Exception as e:
            self.logger.error(f"Failed to connect to Arduino: {e}")
            raise

    async def init_scanner(self):
        try:
            reader, _ = await serial_asyncio.open_serial_connection(url=SCANNER_PORT, baudrate=BAUDRATE)
            self.logger.info(f"Connected to Scanner on {SCANNER_PORT}")
            return reader
        except Exception as e:
            self.logger.error(f"Failed to connect to Scanner: {e}")
            raise

    async def send_to_arduino(self, cmd: str):
        """Safely write a command to Arduino (thread-safe via _serial_lock)."""
        if not self.serial_writer:
            self.logger.warning("Arduino not connected")
            return

        async with self._serial_lock:
            try:
                self.serial_writer.write(f"{cmd}\n".encode())
                await self.serial_writer.drain()
                self.logger.info(f"Sent to Arduino: {cmd}")
            except Exception as e:
                self.logger.error(f"Arduino write error: {e}")

    async def serial_listener(self, reader):
        """Listen for messages from Arduino and react accordingly."""
        while not self._shutdown_event.is_set():
            try:
                line = await reader.readline()
                if not line:
                    await asyncio.sleep(0.1)
                    continue
                msg = line.decode(errors="ignore").strip()
                if not msg:
                    continue
                self.logger.info(f"Arduino says: {msg}")
                if msg == "SESSION_TIMEOUT" and self.session_active:
                    await self.end_session()
            except Exception as e:
                self.logger.error(f"Serial read error: {e}")
                await asyncio.sleep(1)

    # ------------------ WebSocket ------------------
    async def send_message(self, message: dict):
        """Send message to server if connected."""
        if self.websocket and not getattr(self.websocket, "closed", False):
            try:
                await self.websocket.send(json.dumps(message))
                self.logger.info(f"Sent: {message}")
            except Exception as e:
                self.logger.error(f"Failed to send message: {e}")
        else:
            self.logger.warning("WebSocket not connected; message not sent")

    async def authenticate(self):
        hello_message = {
            "type": "HELLO",
            "fandomat_id": FANDOMAT_ID,
            "device_token": DEVICE_TOKEN,
            "version": VERSION,
        }
        await self.send_message(hello_message)

    def _next_bottle_code(self) -> str:
        self.bottle_counter += 1
        return f"BTL-{FANDOMAT_ID:03d}-{self.bottle_counter:05d}"

    async def check_bottle(self, sku: str):
        await self.send_message({"type": "CHECK_BOTTLE", "session_id": self.current_session_id, "sku": sku})

    async def accept_bottle(self, material: str):
        msg = {
            "type": "BOTTLE_ACCEPTED",
            "session_id": self.current_session_id,
            "code": self._next_bottle_code(),
            "material": material,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        await self.send_message(msg)

    # ------------------ Session timeout ------------------
    async def _cancel_session_timeout(self):
        if self.session_timeout_task and not self.session_timeout_task.done():
            self.session_timeout_task.cancel()
            try:
                await self.session_timeout_task
            except asyncio.CancelledError:
                pass
        self.session_timeout_task = None

    async def start_session_timeout(self):
        await self._cancel_session_timeout()
        self.session_timeout_task = asyncio.create_task(self.session_timeout_handler())

    async def session_timeout_handler(self):
        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=SESSION_TIMEOUT)
        except asyncio.TimeoutError:
            if self.session_active:
                self.logger.info("Session timeout reached")
                await self.end_session()

    async def end_session(self):
        if not self.session_active or not self.current_session_id:
            return
        self.session_active = False
        await self._cancel_session_timeout()
        await self.send_message({"type": "SESSION_END", "session_id": self.current_session_id})
        await self.send_to_arduino("E")
        self.logger.info(f"Session {self.current_session_id} ended")
        self.current_session_id = None

    # ------------------ Scanner ------------------
    async def scanner_listener(self, scanner_reader):
        self.logger.info(f"Listening for scanner data on {SCANNER_PORT}")
        # Prefer readline() for line-oriented scanners; fallback to buffered read if needed.
        buffer = bytearray()
        use_readline = hasattr(scanner_reader, "readline")

        while not self._shutdown_event.is_set():
            try:
                if use_readline:
                    raw = await scanner_reader.readline()
                    if not raw:
                        await asyncio.sleep(0.01)
                        continue
                    try:
                        line = raw.decode(errors="ignore").strip()
                    except Exception:
                        line = raw.decode("utf-8", "replace").strip()

                    self.logger.debug(f"Raw scanner bytes: {raw!r}")
                    if line:
                        self.logger.info(f"Scanner read: {line}")
                        if self.session_active and self.current_session_id:
                            await self.check_bottle(line)
                            await self.start_session_timeout()
                else:
                    # fallback: read chunks and split on CR/LF
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
                        if line:
                            self.logger.info(f"Scanner read: {line}")
                            if self.session_active and self.current_session_id:
                                await self.check_bottle(line)
                                await self.start_session_timeout()
            except Exception as e:
                self.logger.error(f"Scanner error: {e}")
                await asyncio.sleep(0.1)

    # ------------------ Message handling ------------------
    async def handle_message(self, message: dict) -> bool:
        msg_type = message.get("type")
        self.logger.info(f"Received: {message}")

        if msg_type == "OK":
            if not self.authenticated and "успешно подключен" in message.get("message", ""):
                self.authenticated = True
                self.logger.info("Authentication successful")
            else:
                self.logger.info(f"OK: {message.get('message')}")
            return True

        if msg_type == "ERROR":
            self.logger.error(f"Server error: {message.get('error')}")
            if not self.authenticated:
                return False
            return True

        if msg_type == "PING":
            # reply quickly
            await self.send_message({"type": "PONG"})
            return True

        if msg_type == "START_SESSION":
            session_id = message.get("session_id")
            user_id = message.get("user_id")
            self.current_session_id = session_id
            self.session_active = True
            self.logger.info(f"Starting session {session_id} for user {user_id}")
            await self.send_to_arduino("S")
            await self.send_message({"type": "SESSION_STARTED", "session_id": session_id})
            await self.start_session_timeout()
            return True

        if msg_type == "CANCEL_SESSION":
            session_id = message.get("session_id")
            reason = message.get("reason", "Unknown")
            if session_id == self.current_session_id:
                self.logger.info(f"Session {session_id} cancelled: {reason}")
                self.session_active = False
                self.current_session_id = None
                await self._cancel_session_timeout()
                await self.send_to_arduino("E")
            return True

        if msg_type == "BOTTLE_CHECK_RESULT":
            session_id = message.get("session_id")
            exists = message.get("exist", False)
            if session_id != self.current_session_id:
                self.logger.warning("BOTTLE_CHECK_RESULT for non-current session")
                return True
            if exists:
                bottle = message.get("bottle", {})
                material = bottle.get("material", "").lower()
                name = bottle.get("name", "Unknown")
                self.logger.info(f"Bottle accepted: {name} ({material})")
                arduino_cmd = "P" if material == "plastic" else "A" if material == "aluminum" else "R"
                await self.send_to_arduino(arduino_cmd)
                if material in ("plastic", "aluminum"):
                    await self.accept_bottle(material)
            else:
                self.logger.warning("Bottle not found in database")
                await self.send_to_arduino("R")
            return True

        self.logger.warning(f"Unknown message type: {msg_type}")
        return True

    # ------------------ WebSocket lifecycle ------------------
    async def websocket_handler(self):
        backoff = 1
        while not self._shutdown_event.is_set():
            try:
                self.logger.info(f"Connecting to WebSocket: {WS_URL}")
                async with websockets.connect(WS_URL, ping_interval=None) as ws:
                    self.websocket = ws
                    self.authenticated = False
                    self.logger.info("WebSocket connected")
                    await self.authenticate()
                    backoff = 1
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                            cont = await self.handle_message(data)
                            if not cont:
                                self.logger.error("Stopping websocket loop due to handler signal")
                                break
                        except json.JSONDecodeError as e:
                            self.logger.error(f"Invalid JSON received: {e}")
            except Exception as e:
                self.logger.warning(f"WebSocket error / disconnected: {e}")
            # reconnect with backoff
            wait = min(backoff, 60)
            self.logger.info(f"Reconnecting in {wait} seconds...")
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=wait)
                break
            except asyncio.TimeoutError:
                backoff *= 2

    # ------------------ Startup / shutdown ------------------
    async def start(self):
        self.logger.info("Starting Fandomat system...")
        arduino_reader = await self.init_arduino()
        scanner_reader = await self.init_scanner()

        tasks = [
            asyncio.create_task(self.websocket_handler(), name="ws"),
            asyncio.create_task(self.serial_listener(arduino_reader), name="serial_reader"),
            asyncio.create_task(self.scanner_listener(scanner_reader), name="scanner_reader"),
        ]

        # wait until shutdown requested
        await self._shutdown_event.wait()

        # on shutdown cancel tasks
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self):
        self.logger.info("Shutdown initiated")
        self._shutdown_event.set()
        await self._cancel_session_timeout()
        # try to close websocket
        if self.websocket and not getattr(self.websocket, "closed", False):
            try:
                await self.websocket.close()
            except Exception:
                pass


async def main():
    fandomat = Fandomat()

    loop = asyncio.get_running_loop()

    # handle signals (POSIX)
    try:
        for sig in (asyncio.Signals.SIGINT, asyncio.Signals.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(fandomat.stop()))
    except Exception:
        # Windows or environments without signals support
        pass

    try:
        await fandomat.start()
    except Exception as e:
        fandomat.logger.error(f"Failed to start system: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # graceful exit
        logging.getLogger().info("Program stopped by user")
    except Exception as e:
        logging.getLogger().error(f"Program crashed: {e}")