from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path


DEFAULT_BASE_IP = "10.10.3.49:8000"  # Legacy HTTP paths (optional)
DEFAULT_DEVICE_NUMBER = "0f00b3d8-f6e2-4e0d-8a7b-61e0838c8f6f"  # Legacy
DEFAULT_ARDUINO_PORT = "/dev/ttyUSB0"
DEFAULT_SCANNER_PORT = "/dev/ttyACM0"
DEFAULT_BAUDRATE = 9600
DEFAULT_LOG_DIR = "logs"
DEFAULT_WS_URL = "wss://api.yaxshi.link/ws/fandomats"
DEFAULT_VERSION = "1.0.0"


CONFIG_PATH = Path("config.json")


@dataclass
class Config:
    arduino_port: str = DEFAULT_ARDUINO_PORT
    scanner_port: str = DEFAULT_SCANNER_PORT
    baudrate: int = DEFAULT_BAUDRATE
    log_dir: str = DEFAULT_LOG_DIR
    ws_url: str = DEFAULT_WS_URL
    fandomat_id: int = 0
    device_token: str = ""
    version: str = DEFAULT_VERSION

    # No legacy HTTP URLs; WebSocket endpoint is stored directly in ws_url


def load_config() -> Config:
    """Load config from config.json; ignore unknown legacy keys."""
    cfg = Config()
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            field_names = {f.name for f in fields(Config)}
            for k in field_names:
                if k in data:
                    setattr(cfg, k, data[k])
        except Exception:
            # Fall back to defaults if file corrupt
            return cfg
    return cfg


def save_config(cfg: Config) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg.__dict__, indent=2, ensure_ascii=False), encoding="utf-8"
    )
