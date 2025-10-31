import asyncio
import json
import websockets
import serial_asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid
import os

# ------------------ CONFIG ------------------
# Defaults (kept for backward compatibility)
WS_URL = "wss://api.yaxshi.link/ws/fandomats"
FANDOMAT_ID = 3
DEVICE_TOKEN = "fnd_a7b3c9d2e8f4g1h5i6j7k8l9m0n1"
VERSION = "1.0.0"

ARDUINO_PORT = "/dev/ttyUSB0"
SCANNER_PORT = "/dev/ttyACM0"
BAUDRATE = 9600

SESSION_TIMEOUT = 90

# Load overrides from config.json (if present) and environment variables.
# Priority: environment variables > config.json > defaults above.
CONFIG_PATH = Path("config.json")
if CONFIG_PATH.exists():
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        WS_URL = cfg.get("WS_URL", WS_URL)
        FANDOMAT_ID = cfg.get("FANDOMAT_ID", FANDOMAT_ID)
        DEVICE_TOKEN = cfg.get("DEVICE_TOKEN", DEVICE_TOKEN)
        VERSION = cfg.get("VERSION", VERSION)

        ARDUINO_PORT = cfg.get("ARDUINO_PORT", ARDUINO_PORT)
        SCANNER_PORT = cfg.get("SCANNER_PORT", SCANNER_PORT)
        BAUDRATE = cfg.get("BAUDRATE", BAUDRATE)
        SESSION_TIMEOUT = cfg.get("SESSION_TIMEOUT", SESSION_TIMEOUT)
    except Exception as e:
        # If config parsing fails, keep defaults and log later
        print(f"Warning: failed to read config.json: {e}")

# Environment variables override everything (useful for systemd or Docker)
WS_URL = os.getenv("WS_URL", WS_URL)
FANDOMAT_ID = int(os.getenv("FANDOMAT_ID", str(FANDOMAT_ID)))
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", DEVICE_TOKEN)
VERSION = os.getenv("VERSION", VERSION)

ARDUINO_PORT = os.getenv("ARDUINO_PORT", ARDUINO_PORT)
SCANNER_PORT = os.getenv("SCANNER_PORT", SCANNER_PORT)
BAUDRATE = int(os.getenv("BAUDRATE", str(BAUDRATE)))
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", str(SESSION_TIMEOUT)))

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ------------------ STATE ------------------
websocket = None
authenticated = False
current_session_id: Optional[str] = None
session_active = False
serial_writer = None
bottle_counter = 0
session_timeout_task = None
loggers = {}

# ------------------ LOGGING ------------------
def get_logger(name: str = "system") -> logging.Logger:
    """Create or get a logger instance."""
    log_file = LOG_DIR / f"{name}.log"
    
    if name not in loggers:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
        logger.addHandler(handler)
        
        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
        logger.addHandler(console_handler)
        
        loggers[name] = logger
    
    return loggers[name]

# ------------------ SERIAL CONNECTIONS ------------------
async def init_arduino():
    """Initialize Arduino serial connection."""
    global serial_writer
    try:
        reader, serial_writer = await serial_asyncio.open_serial_connection(url=ARDUINO_PORT, baudrate=BAUDRATE)
        logger = get_logger()
        logger.info(f"Connected to Arduino on {ARDUINO_PORT}")
        return reader, serial_writer
    except Exception as e:
        logger = get_logger()
        logger.error(f"Failed to connect to Arduino: {e}")
        raise

async def init_scanner():
    """Initialize Scanner serial connection."""
    try:
        reader, _ = await serial_asyncio.open_serial_connection(url=SCANNER_PORT, baudrate=BAUDRATE)
        logger = get_logger()
        logger.info(f"Connected to Scanner on {SCANNER_PORT}")
        return reader
    except Exception as e:
        logger = get_logger()
        logger.error(f"Failed to connect to Scanner: {e}")
        raise

# ------------------ ARDUINO HANDLERS ------------------
async def send_to_arduino(cmd: str):
    """Send a command to Arduino."""
    if not serial_writer:
        logger = get_logger()
        logger.warning("Arduino not connected")
        return
    
    try:
        serial_writer.write(f"{cmd}\n".encode())
        await serial_writer.drain()
        logger = get_logger()
        logger.info(f"Sent to Arduino: {cmd}")
    except Exception as e:
        logger = get_logger()
        logger.error(f"Arduino write error: {e}")

async def serial_listener(reader):
    """Listen for messages from Arduino."""
    logger = get_logger()
    
    while True:
        try:
            line = await reader.readline()
            msg = line.decode(errors="ignore").strip()
            if not msg:
                continue
            
            logger.info(f"Arduino says: {msg}")
            
            # Handle Arduino messages here if needed
            if msg == "SESSION_TIMEOUT" and session_active:
                await end_session()
                
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            await asyncio.sleep(1)

# ------------------ WEBSOCKET HANDLERS ------------------
async def send_message(message: dict):
    """Send message to WebSocket server."""
    global websocket
    if websocket and not websocket.closed:
        try:
            await websocket.send(json.dumps(message))
            logger = get_logger()
            logger.info(f"Sent: {message}")
        except Exception as e:
            logger = get_logger()
            logger.error(f"Failed to send message: {e}")

async def authenticate():
    """Send HELLO message for authentication."""
    hello_message = {
        "type": "HELLO",
        "fandomat_id": FANDOMAT_ID,
        "device_token": DEVICE_TOKEN,
        "version": VERSION
    }
    await send_message(hello_message)

def generate_bottle_code() -> str:
    """Generate unique bottle code."""
    global bottle_counter
    bottle_counter += 1
    return f"BTL-{FANDOMAT_ID:03d}-{bottle_counter:05d}"

async def check_bottle(sku: str) -> dict:
    """Check if bottle SKU exists in database."""
    check_message = {
        "type": "CHECK_BOTTLE",
        "session_id": current_session_id,
        "sku": sku
    }
    await send_message(check_message)

async def accept_bottle(material: str):
    """Send BOTTLE_ACCEPTED message."""
    bottle_message = {
        "type": "BOTTLE_ACCEPTED",
        "session_id": current_session_id,
        "code": generate_bottle_code(),
        "material": material,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    await send_message(bottle_message)

async def start_session_timeout():
    """Start session timeout timer."""
    global session_timeout_task
    if session_timeout_task:
        session_timeout_task.cancel()
    
    session_timeout_task = asyncio.create_task(session_timeout_handler())

async def session_timeout_handler():
    """Handle session timeout after 90 seconds of inactivity."""
    try:
        await asyncio.sleep(SESSION_TIMEOUT)
        if session_active:
            logger = get_logger()
            logger.info("Session timeout reached")
            await end_session()
    except asyncio.CancelledError:
        pass

async def end_session():
    """End current session."""
    global session_active, current_session_id, session_timeout_task
    
    if not session_active or not current_session_id:
        return
    
    session_active = False
    
    # Cancel timeout task
    if session_timeout_task:
        session_timeout_task.cancel()
        session_timeout_task = None
    
    # Send SESSION_END message
    end_message = {
        "type": "SESSION_END",
        "session_id": current_session_id
    }
    await send_message(end_message)
    
    # Close bottle acceptor
    await send_to_arduino("E")
    
    logger = get_logger()
    logger.info(f"Session {current_session_id} ended")
    current_session_id = None

# ------------------ SCANNER HANDLER ------------------
async def scanner_listener(scanner_reader):
    """Read barcodes from scanner and process them."""
    logger = get_logger()
    logger.info(f"Listening for scanner data on {SCANNER_PORT}")
    buffer = bytearray()
    
    while True:
        try:
            chunk = await scanner_reader.read(128)
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
                    logger.info(f"Scanner read: {line}")
                    if session_active and current_session_id:
                        await check_bottle(line)
                        # Reset session timeout on activity
                        await start_session_timeout()
        except Exception as e:
            logger.error(f"Scanner error: {e}")
            await asyncio.sleep(0.1)

# ------------------ MESSAGE HANDLERS ------------------
async def handle_message(message: dict):
    """Handle incoming WebSocket messages."""
    global authenticated, session_active, current_session_id
    logger = get_logger()
    
    msg_type = message.get("type")
    logger.info(f"Received: {message}")
    
    if msg_type == "OK":
        if not authenticated and "успешно подключен" in message.get("message", ""):
            authenticated = True
            logger.info("Authentication successful")
        elif session_active:
            logger.info(f"Server response: {message.get('message')}")
    
    elif msg_type == "ERROR":
        logger.error(f"Server error: {message.get('error')}")
        if not authenticated:
            logger.error("Authentication failed, stopping...")
            return False
    
    elif msg_type == "PING":
        # Respond with PONG
        await send_message({"type": "PONG"})
    
    elif msg_type == "START_SESSION":
        session_id = message.get("session_id")
        user_id = message.get("user_id")
        current_session_id = session_id
        session_active = True
        
        logger.info(f"Starting session {session_id} for user {user_id}")
        
        # Open bottle acceptor
        await send_to_arduino("S")
        
        # Send confirmation
        await send_message({
            "type": "SESSION_STARTED",
            "session_id": session_id
        })
        
        # Start session timeout
        await start_session_timeout()
    
    elif msg_type == "CANCEL_SESSION":
        session_id = message.get("session_id")
        reason = message.get("reason", "Unknown")
        
        if session_id == current_session_id:
            logger.info(f"Session {session_id} cancelled: {reason}")
            session_active = False
            current_session_id = None
            
            # Cancel timeout task
            if session_timeout_task:
                session_timeout_task.cancel()
            
            # Close bottle acceptor
            await send_to_arduino("E")
    
    elif msg_type == "BOTTLE_CHECK_RESULT":
        session_id = message.get("session_id")
        exists = message.get("exist", False)
        
        if session_id == current_session_id:
            if exists:
                bottle = message.get("bottle", {})
                material = bottle.get("material", "").lower()
                name = bottle.get("name", "Unknown")
                
                logger.info(f"Bottle accepted: {name} ({material})")
                
                # Map material to Arduino command
                arduino_cmd = "P" if material == "plastic" else "A" if material == "aluminum" else "R"
                await send_to_arduino(arduino_cmd)
                
                # Send BOTTLE_ACCEPTED
                if material in ["plastic", "aluminum"]:
                    await accept_bottle(material)
            else:
                logger.warning("Bottle not found in database")
                await send_to_arduino("R")  # Reject bottle
    
    return True

# ------------------ WEBSOCKET CONNECTION ------------------
async def websocket_handler():
    """Handle WebSocket connection and messages."""
    global websocket, authenticated
    logger = get_logger()
    
    while True:
        try:
            logger.info(f"Connecting to WebSocket: {WS_URL}")
            async with websockets.connect(WS_URL) as ws:
                websocket = ws
                authenticated = False
                logger.info("WebSocket connected")
                
                # Send authentication
                await authenticate()
                
                # Listen for messages
                async for message in ws:
                    try:
                        data = json.loads(message)
                        should_continue = await handle_message(data)
                        if not should_continue:
                            break
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON received: {e}")
                    except Exception as e:
                        logger.error(f"Error handling message: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        
        logger.info("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)

# ------------------ MAIN ------------------
async def main():
    """Main function to start all components."""
    logger = get_logger()
    logger.info("Starting Fandomat system...")
    
    try:
        # Initialize hardware connections
        arduino_reader, _ = await init_arduino()
        scanner_reader = await init_scanner()
        
        # Start all tasks
        await asyncio.gather(
            websocket_handler(),
            serial_listener(arduino_reader),
            scanner_listener(scanner_reader)
        )
    except Exception as e:
        logger.error(f"Failed to start system: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger = get_logger()
        logger.info("Program stopped by user")
    except Exception as e:
        logger = get_logger()
        logger.error(f"Program crashed: {e}")