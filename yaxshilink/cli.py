from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from .config import Config, save_config, normalize_base_url


def _list_serial_by_id() -> List[str]:
    by_id = Path("/dev/serial/by-id")
    if by_id.is_dir():
        try:
            return sorted(str(p) for p in by_id.iterdir())
        except Exception:
            pass
    # fallback: direct tty devices
    dev = Path("/dev")
    candidates = list(dev.glob("ttyUSB*")) + list(dev.glob("ttyACM*"))
    return sorted(str(p) for p in candidates)


def _input_with_default(prompt: str, default: str) -> str:
    raw = input(f"{prompt} [{default}]: ").strip()
    return raw or default


def _pick_from_list(title: str, items: List[str], default: Optional[str] = None) -> str:
    print(f"\n{title}")
    for i, it in enumerate(items, start=1):
        print(f"  {i}) {it}")
    choice = input(f"Select (1-{len(items)}) or enter custom path [{default or '1'}]: ").strip()
    if not choice:
        return default or items[0]
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(items):
            return items[idx - 1]
    # Treat as custom path
    return choice


def validate_host_port(s: str) -> bool:
    # Basic check host:port or ip:port
    return bool(re.match(r"^[^:/\s]+(:\d+)?$", s))


def setup(config_path: Optional[str] = None):
    print("YaxshiLink setup wizard")
    print("This will create a configuration file for the service.")

    defaults = Config()

    while True:
        base_in = _input_with_default(
            "Server base URL (host:port or full URL, e.g. https://api.yaxshi.link)",
            getattr(defaults, "base_url", "http://10.10.3.49:8000"),
        )
        # accept either full URL or host:port
        if "://" in base_in or validate_host_port(base_in):
            base_url = normalize_base_url(base_in)
            break
        print("Invalid input. Provide host:port or full URL like https://domain")

    device_number = _input_with_default("Device UUID/number", defaults.device_number)

    serials = _list_serial_by_id()
    if not serials:
        print("No serial devices found. You can enter paths manually.")
        arduino_port = _input_with_default("Arduino serial port", defaults.arduino_port)
        scanner_port = _input_with_default("Scanner serial port", defaults.scanner_port)
    else:
        arduino_port = _pick_from_list("Available serial devices (Arduino)", serials, default=serials[0])
        scanner_port = _pick_from_list("Available serial devices (Scanner)", serials, default=serials[-1])

    while True:
        baud = _input_with_default("Baudrate", str(defaults.baudrate))
        try:
            baudrate = int(baud)
            break
        except ValueError:
            print("Enter a valid integer baudrate")

    print("\nWhere to save config?")
    if os.geteuid() == 0:
        default_path = Path("/etc/yaxshilink/config.json")
    else:
        default_path = Path.home() / ".config/yaxshilink/config.json"

    target = input(f"Config file path [{default_path}]: ").strip() or str(default_path)
    cfg = Config(
        base_url=base_url,
        device_number=device_number,
        arduino_port=arduino_port,
        scanner_port=scanner_port,
        baudrate=baudrate,
    )
    save_config(cfg, Path(target))
    print(f"Saved configuration to {target}")


if __name__ == "__main__":
    setup()
