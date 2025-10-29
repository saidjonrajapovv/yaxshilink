from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


DEFAULT_CONFIG_DIRS = [
    Path(os.environ.get("YAXSHILINK_CONFIG", "")),
    Path("/etc/yaxshilink/config.json"),
    Path.home() / ".config/yaxshilink/config.json",
]


@dataclass
class Config:
    base_url: str = "http://10.10.3.49:8000"
    # New protocol fields
    fandomat_id: int = 0
    device_token: str = "CHANGE-ME-TOKEN"
    version: str = "1.0.0"
    # Legacy/optional
    device_number: str = "CHANGE-ME-DEVICE-ID"
    arduino_port: str = "/dev/ttyUSB0"
    scanner_port: str = "/dev/ttyACM0"
    baudrate: int = 9600
    log_dir: Optional[str] = None  # if None, app will choose a sensible default
    quiet_terminal: bool = True  # minimize terminal noise, show only special lines

    @property
    def http_base(self) -> str:
        # Ensure scheme is http/https and no trailing slash
        return normalize_http_base(self.base_url)

    @property
    def api_check_url(self) -> str:
        # kept for backward compatibility; new protocol uses WS
        return join_url(self.http_base, "/api/bottle/check/")

    def session_item_url(self, session_id: int) -> str:
        # kept for backward compatibility; new protocol uses WS
        return join_url(self.http_base, f"/api/session/{session_id}/items/")

    @property
    def ws_url(self) -> str:
        # New protocol fixed path
        return build_ws_url(self.base_url, "/ws/fandomats")


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
        "base_url": os.environ.get("YAX_BASE_URL"),
        "base_ip": os.environ.get("YAX_BASE_IP"),  # backward-compat
        "fandomat_id": os.environ.get("YAX_FANDOMAT_ID"),
        "device_token": os.environ.get("YAX_DEVICE_TOKEN"),
        "version": os.environ.get("YAX_VERSION"),
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
        elif k == "fandomat_id":
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

    # Normalize base URL
    base_url = data.get("base_url")
    base_ip = data.get("base_ip")
    if base_url:
        data["base_url"] = normalize_base_url(base_url)
    elif base_ip:
        data["base_url"] = normalize_base_url(base_ip)

    # Drop legacy key if present
    data.pop("base_ip", None)

    cfg = Config(**{**asdict(Config()), **data})
    return cfg


def save_config(cfg: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Only persist user-settable fields
    serializable = {
        "base_url": cfg.base_url,
        # New protocol fields
        "fandomat_id": cfg.fandomat_id,
        "device_token": cfg.device_token,
        "version": cfg.version,
        # Legacy/optional
        "device_number": cfg.device_number,
        "arduino_port": cfg.arduino_port,
        "scanner_port": cfg.scanner_port,
        "baudrate": cfg.baudrate,
        "log_dir": cfg.log_dir,
    }
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_base_url(s: str) -> str:
    """Accept host:port, http(s)://host[:port], or ws(s)://host[:port];
    return canonical http(s)://host[:port] without trailing slash.
    """
    s = s.strip()
    if not s:
        return "http://localhost"
    if "://" not in s:
        # host[:port]
        return f"http://{s}".rstrip("/")
    p = urlparse(s)
    if p.scheme in ("http", "https"):
        return f"{p.scheme}://{p.netloc}".rstrip("/")
    if p.scheme == "ws":
        return f"http://{p.netloc}".rstrip("/")
    if p.scheme == "wss":
        return f"https://{p.netloc}".rstrip("/")
    # default to http
    return f"http://{p.netloc or s}".rstrip("/")


def normalize_http_base(base_url: str) -> str:
    base = normalize_base_url(base_url)
    return base.rstrip("/")


def join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def build_ws_url(base_url: str, path: str) -> str:
    http = normalize_http_base(base_url)
    parsed = urlparse(http)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{ws_scheme}://{parsed.netloc}{path}"
