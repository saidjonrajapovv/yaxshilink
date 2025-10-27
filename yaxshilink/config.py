from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


DEFAULT_CONFIG_DIRS = [
    Path(os.environ.get("YAXSHILINK_CONFIG", "")),
    Path("/etc/yaxshilink/config.json"),
    Path.home() / ".config/yaxshilink/config.json",
]


@dataclass
class Config:
    base_ip: str = "10.10.3.49:8000"
    device_number: str = "CHANGE-ME-DEVICE-ID"
    arduino_port: str = "/dev/ttyUSB0"
    scanner_port: str = "/dev/ttyACM0"
    baudrate: int = 9600
    log_dir: Optional[str] = None  # if None, app will choose a sensible default
    quiet_terminal: bool = True  # minimize terminal noise, show only special lines

    @property
    def api_check_url(self) -> str:
        return f"http://{self.base_ip}/api/bottle/check/"

    def session_item_url(self, session_id: int) -> str:
        return f"http://{self.base_ip}/api/session/{session_id}/items/"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.base_ip}/ws/device/{self.device_number}/"


def _load_json_if_exists(path: Path) -> Optional[dict]:
    try:
        if path and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def load_config(explicit_path: Optional[Path] = None) -> Config:
    """Load configuration from:
    1) explicit_path (if provided)
    2) YAXSHILINK_CONFIG env path
    3) /etc/yaxshilink/config.json
    4) ~/.config/yaxshilink/config.json

    Environment variable overrides (if set) take precedence for individual keys:
      - YAX_BASE_IP, YAX_DEVICE_NUMBER, YAX_ARDUINO_PORT, YAX_SCANNER_PORT, YAX_BAUDRATE, YAX_LOG_DIR
    """
    data: dict = {}

    candidates = [explicit_path] if explicit_path else DEFAULT_CONFIG_DIRS
    for p in candidates:
        if not p:
            continue
        d = _load_json_if_exists(p)
        if d:
            data.update(d)
            break

    # Apply env overrides if present
    env_map = {
        "base_ip": os.environ.get("YAX_BASE_IP"),
        "device_number": os.environ.get("YAX_DEVICE_NUMBER"),
        "arduino_port": os.environ.get("YAX_ARDUINO_PORT"),
        "scanner_port": os.environ.get("YAX_SCANNER_PORT"),
        "baudrate": os.environ.get("YAX_BAUDRATE"),
        "log_dir": os.environ.get("YAX_LOG_DIR"),
        "quiet_terminal": os.environ.get("YAX_QUIET_TERMINAL"),
    }

    for k, v in env_map.items():
        if v is None:
            continue
        if k == "baudrate":
            try:
                data[k] = int(v)
            except ValueError:
                pass
        elif k == "quiet_terminal":
            lv = str(v).strip().lower()
            if lv in ("1", "true", "yes", "on"):  # default True
                data[k] = True
            elif lv in ("0", "false", "no", "off"):
                data[k] = False
        else:
            data[k] = v

    cfg = Config(**{**asdict(Config()), **data})
    return cfg


def save_config(cfg: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Only persist user-settable fields
    serializable = {
        "base_ip": cfg.base_ip,
        "device_number": cfg.device_number,
        "arduino_port": cfg.arduino_port,
        "scanner_port": cfg.scanner_port,
        "baudrate": cfg.baudrate,
        "log_dir": cfg.log_dir,
    }
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
