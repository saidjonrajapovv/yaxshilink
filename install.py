#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import platform
import time
from typing import Optional


PROJECT_ROOT = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_ROOT / ".venv"
PYTHON_BIN = VENV_DIR / "bin" / "python"
PIP_BIN = VENV_DIR / "bin" / "pip"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = LAUNCH_AGENTS / "com.yaxshilink.device.plist"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd or PROJECT_ROOT), check=check)


def recreate_venv():
    if VENV_DIR.exists():
        print(f"Removing existing venv: {VENV_DIR}")
        shutil.rmtree(VENV_DIR)
    print("Creating virtual environment…")
    try:
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    except subprocess.CalledProcessError:
        # Likely missing python3-venv on Debian/Raspberry Pi
        if platform.system() == "Linux":
            print("python3-venv paketi kerak. O'rnataymi? (sudo bilan)")
            ans = input("[Y/n]: ").strip().lower()
            if ans in ("", "y", "yes"):
                run(["sudo", "apt-get", "update"], check=True)
                run(["sudo", "apt-get", "install", "-y", "python3-venv"], check=True)
                subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
            else:
                print("❌ Venv yaratilmaydi. Avval python3-venv o'rnating.")
                sys.exit(1)
        else:
            raise
    print("Installing requirements…")
    run([str(PIP_BIN), "install", "--upgrade", "pip", "wheel", "setuptools"])
    run([str(PIP_BIN), "install", "-r", "requirements.txt"]) 


def list_serial_ports() -> list[str]:
    """List serial ports using local Python; fallback to venv Python if needed."""
    try:
        from serial.tools import list_ports  # type: ignore

        return [p.device for p in list_ports.comports()]
    except Exception:
        # Fallback to venv python if available
        if PYTHON_BIN.exists():
            code = (
                "import json; from serial.tools import list_ports;"
                "print(json.dumps([p.device for p in list_ports.comports()]))"
            )
            try:
                out = subprocess.check_output([str(PYTHON_BIN), "-c", code], text=True)
                return json.loads(out)
            except Exception:
                return []
        return []


def prompt(text: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{text}{suffix}: ").strip()
    return val or (default or "")


def prompt_config():
    from app.config import (
        Config,
        DEFAULT_ARDUINO_PORT,
        DEFAULT_SCANNER_PORT,
        DEFAULT_BAUDRATE,
        DEFAULT_WS_URL,
        DEFAULT_VERSION,
        save_config,
    )

    print("\n— Konfiguratsiya —")
    ws_url = prompt("WS URL", DEFAULT_WS_URL)
    fandomat_id_s = prompt("FANDOMAT_ID (raqam)", "0")
    try:
        fandomat_id = int(fandomat_id_s)
    except ValueError:
        fandomat_id = 0
    device_token = prompt("DEVICE_TOKEN (admin paneldan)", "")
    version = prompt("FIRMWARE VERSION", DEFAULT_VERSION)
    baudrate_s = prompt("BAUDRATE", str(DEFAULT_BAUDRATE))
    try:
        baudrate = int(baudrate_s)
    except ValueError:
        baudrate = DEFAULT_BAUDRATE

    print("\nSerial portlarni qidiryapman…")
    ports = list_serial_ports()
    if not ports:
        print("⚠️ Hech qanday serial port topilmadi. Qurilmalarni ulang va qayta urinib ko'ring.")
        ports = [DEFAULT_ARDUINO_PORT, DEFAULT_SCANNER_PORT]

    def choose(label: str, default_value: str) -> str:
        print(f"\n{label} uchun portni tanlang:")
        for i, p in enumerate(ports, start=1):
            print(f"  {i}) {p}")
        choice = input(f"Raqamni kiriting (yoki to'g'ridan-to'g'ri port yozing) [{default_value}]: ").strip()
        if not choice:
            return default_value
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                return ports[idx]
        return choice

    arduino_port = choose("Arduino", DEFAULT_ARDUINO_PORT)
    scanner_port = choose("Scanner", DEFAULT_SCANNER_PORT)

    cfg = Config(
        arduino_port=arduino_port,
        scanner_port=scanner_port,
        baudrate=baudrate,
        ws_url=ws_url,
        fandomat_id=fandomat_id,
        device_token=device_token,
        version=version,
    )
    save_config(cfg)
    print("✅ config.json yozildi.")


def config_show():
    from app.config import load_config

    cfg = load_config()
    print(json.dumps(cfg.__dict__, indent=2, ensure_ascii=False))


def config_set(
    arduino_port: Optional[str],
    scanner_port: Optional[str],
    baudrate: Optional[int],
    log_dir: Optional[str],
    ws_url: Optional[str],
    fandomat_id: Optional[int],
    device_token: Optional[str],
    version: Optional[str],
):
    from app.config import load_config, save_config

    cfg = load_config()
    if arduino_port:
        cfg.arduino_port = arduino_port
    if scanner_port:
        cfg.scanner_port = scanner_port
    if baudrate is not None:
        cfg.baudrate = baudrate
    if log_dir:
        cfg.log_dir = log_dir
    if ws_url:
        cfg.ws_url = ws_url
    if fandomat_id is not None:
        cfg.fandomat_id = fandomat_id
    if device_token is not None:
        cfg.device_token = device_token
    if version:
        cfg.version = version
    save_config(cfg)
    print("✅ config.json yangilandi.")


def make_plist() -> str:
    logs_path = PROJECT_ROOT / "logs"
    logs_path.mkdir(exist_ok=True)
    logs_dir = logs_path.as_posix()
    python_exe = PYTHON_BIN.as_posix()
    script = (PROJECT_ROOT / "main.py").as_posix()
    working_dir = PROJECT_ROOT.as_posix()

    return f"""
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yaxshilink.device</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_exe}</string>
        <string>{script}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{logs_dir}/service.out.log</string>
    <key>StandardErrorPath</key>
    <string>{logs_dir}/service.err.log</string>
</dict>
</plist>
""".strip()


def install_service_macos():
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(make_plist(), encoding="utf-8")
    print(f"Plist yozildi: {PLIST_PATH}")
    run(["launchctl", "load", str(PLIST_PATH)], check=False)
    run(["launchctl", "start", "com.yaxshilink.device"], check=False)
    print("✅ Service ishga tushdi.")


def remove_service_macos():
    if PLIST_PATH.exists():
        run(["launchctl", "stop", "com.yaxshilink.device"], check=False)
        run(["launchctl", "unload", str(PLIST_PATH)], check=False)
        PLIST_PATH.unlink(missing_ok=True)
        print("🗑️ Service o'chirildi.")
    else:
        print("Service topilmadi.")


def service_status_macos():
    run(["launchctl", "list"], check=False)


def make_systemd_unit(user_name: str | None = None) -> str:
    logs_path = PROJECT_ROOT / "logs"
    logs_path.mkdir(exist_ok=True)
    python_exe = PYTHON_BIN.as_posix()
    script = (PROJECT_ROOT / "main.py").as_posix()
    working_dir = PROJECT_ROOT.as_posix()
    user_line = f"User={user_name}\n" if user_name else ""

    return f"""
[Unit]
Description=YaxshiLink Device Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
{user_line}WorkingDirectory={working_dir}
ExecStartPre=/bin/mkdir -p {working_dir}/logs
ExecStart={python_exe} {script}
Restart=always
RestartSec=3
StandardOutput=file:{working_dir}/logs/service.out.log
StandardError=file:{working_dir}/logs/service.err.log

[Install]
WantedBy=multi-user.target
""".strip()


def install_service_linux():
    svc_name = "yaxshilink.service"
    unit_tmp = PROJECT_ROOT / svc_name
    # Detect a suitable user to run service under (default: current user)
    try:
        user_name = os.environ.get("SUDO_USER") or os.environ.get("USER")
    except Exception:
        user_name = None
    unit_tmp.write_text(make_systemd_unit(user_name), encoding="utf-8")
    print(f"Systemd unit tayyorlandi: {unit_tmp}")
    # Move with sudo and enable
    run(["sudo", "mv", str(unit_tmp), f"/etc/systemd/system/{svc_name}"])
    run(["sudo", "systemctl", "daemon-reload"], check=False)
    run(["sudo", "systemctl", "enable", "--now", svc_name], check=False)
    print("✅ systemd service ishga tushdi.")


def remove_service_linux():
    svc_name = "yaxshilink.service"
    run(["sudo", "systemctl", "disable", "--now", svc_name], check=False)
    run(["sudo", "rm", "-f", f"/etc/systemd/system/{svc_name}"], check=False)
    run(["sudo", "systemctl", "daemon-reload"], check=False)
    print("🗑️ systemd service o'chirildi.")


def service_status_linux():
    run(["systemctl", "status", "yaxshilink.service"], check=False)


def service_start():
    if is_macos():
        run(["launchctl", "start", "com.yaxshilink.device"], check=False)
    elif is_linux():
        run(["sudo", "systemctl", "start", "yaxshilink.service"], check=False)


def service_stop():
    if is_macos():
        run(["launchctl", "stop", "com.yaxshilink.device"], check=False)
    elif is_linux():
        run(["sudo", "systemctl", "stop", "yaxshilink.service"], check=False)


def service_restart():
    if is_macos():
        service_stop()
        time.sleep(1)
        service_start()
    elif is_linux():
        run(["sudo", "systemctl", "restart", "yaxshilink.service"], check=False)


def is_macos() -> bool:
    return platform.system() == "Darwin"


def is_linux() -> bool:
    return platform.system() == "Linux"


def install_service():
    if is_macos():
        install_service_macos()
    elif is_linux():
        install_service_linux()
    else:
        print("⚠️ Noma'lum OS. Xizmat o'rnatish qo'llab-quvvatlanmaydi.")


def remove_service():
    if is_macos():
        remove_service_macos()
    elif is_linux():
        remove_service_linux()
    else:
        print("⚠️ Noma'lum OS. Xizmatni o'chira olmadim.")


def service_status():
    if is_macos():
        service_status_macos()
    elif is_linux():
        service_status_linux()
    else:
        print("⚠️ Noma'lum OS. Holatni ko'rsatib bo'lmadi.")


def run_app_foreground():
    """Run the app in foreground using venv Python if available."""
    logs_path = PROJECT_ROOT / "logs"
    logs_path.mkdir(exist_ok=True)
    py = PYTHON_BIN if PYTHON_BIN.exists() else Path(sys.executable)
    run([str(py), str(PROJECT_ROOT / "main.py")], check=False)


def test_api(timeout: float = 5.0):
    print("HTTP API testi legacy. Yangi protokol WS orqali ishlaydi. 'test-ws' dan foydalaning.")


def test_ws(timeout: float = 8.0):
    import asyncio
    import websockets  # type: ignore
    from app.config import load_config

    async def _go():
        cfg = load_config()
        print("WS:", cfg.ws_url)
        async with websockets.connect(cfg.ws_url) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "HELLO",
                        "fandomat_id": int(cfg.fandomat_id),
                        "device_token": cfg.device_token,
                        "version": cfg.version,
                    }
                )
            )
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                print("<-", msg)
            except asyncio.TimeoutError:
                print("Javob kelmadi (timeout)")

    asyncio.run(_go())


def test_serial(kind: str, timeout: float = 2.0):
    from app.config import load_config
    import serial  # type: ignore
    import time as _t

    cfg = load_config()
    port = cfg.arduino_port if kind == "arduino" else cfg.scanner_port
    print(f"{kind} portini ochyapman: {port} ({cfg.baudrate})")
    try:
        with serial.Serial(port, cfg.baudrate, timeout=timeout) as s:
            _t.sleep(0.2)
            print("✅ Ochildi.")
    except Exception as e:
        print("❌ Serial xato:", e)


def listen_scanner(seconds: int = 20):
    """Read and print raw data from the configured scanner port for quick diagnostics."""
    from app.config import load_config
    import serial  # type: ignore
    import time as _t

    cfg = load_config()
    port = cfg.scanner_port
    print(f"Scannerni tinglayapman: {port} ({cfg.baudrate}), {seconds}s...")
    try:
        with serial.Serial(port, cfg.baudrate, timeout=0.1) as s:
            start = _t.time()
            buf = bytearray()
            while _t.time() - start < seconds:
                chunk = s.read(128)
                if chunk:
                    buf.extend(chunk)
                    # Print hex preview and ASCII
                    hexp = " ".join(f"{b:02X}" for b in chunk[:32])
                    asc = chunk.decode(errors="ignore").replace("\r", "\\r").replace("\n", "\\n")
                    print(f"[+{_t.time()-start:4.1f}s] HEX: {hexp}{' ...' if len(chunk)>32 else ''}  |  ASCII: {asc}")
                else:
                    _t.sleep(0.02)
            # Try to extract final line if any
            if buf:
                try:
                    text = buf.decode(errors="ignore").strip()
                    if text:
                        print("\nFinal buffer as text:", text)
                except Exception:
                    pass
        print("✅ Tinglash tugadi.")
    except Exception as e:
        print("❌ Tinglash xatosi:", e)


def logs_show(lines: int = 200):
    out = PROJECT_ROOT / "logs" / "service.out.log"
    err = PROJECT_ROOT / "logs" / "service.err.log"

    def tail(p: Path):
        if not p.exists():
            print(f"{p.name} topilmadi")
            return
        content = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in content[-lines:]:
            print(line)

    print("\n---- STDOUT ----")
    tail(out)
    print("\n---- STDERR ----")
    tail(err)


def monitor_ui():
    """Interactive dashboard to show scanner/WS/session events in real-time."""
    from app.config import load_config
    from app.monitor import run_monitor

    cfg = load_config()
    run_monitor(cfg.log_dir)


def main():
    parser = argparse.ArgumentParser(description="YaxshiLink o'rnatish va xizmat boshqaruvi")
    sub = parser.add_subparsers(dest="cmd")

    # Setup
    sub.add_parser("setup", help="Venv yaratish va config sozlash")

    # Ports
    sub.add_parser("ports", help="Serial portlarni ro'yxatlash")

    # Config
    cfg_show = sub.add_parser("config-show", help="Configni ko'rsatish")
    cfg_edit = sub.add_parser("config-edit", help="Configni interaktiv tahrirlash")
    cfg_set = sub.add_parser("config-set", help="Config qiymatlarini parametr orqali o'rnatish")
    cfg_set.add_argument("--arduino-port")
    cfg_set.add_argument("--scanner-port")
    cfg_set.add_argument("--baudrate", type=int)
    cfg_set.add_argument("--log-dir")
    cfg_set.add_argument("--ws-url")
    cfg_set.add_argument("--fandomat-id", type=int)
    cfg_set.add_argument("--device-token")
    cfg_set.add_argument("--version")

    # Service
    sub.add_parser("service-install", help="Xizmatni o'rnatish (macOS/Linux)")
    sub.add_parser("service-remove", help="Xizmatni o'chirish (macOS/Linux)")
    sub.add_parser("service-status", help="Xizmat holatini ko'rish")
    sub.add_parser("service-start", help="Xizmatni ishga tushirish")
    sub.add_parser("service-stop", help="Xizmatni to'xtatish")
    sub.add_parser("service-restart", help="Xizmatni qayta ishga tushirish")

    # Run
    sub.add_parser("run", help="Dasturni foreground rejimida ishga tushirish")

    # Test
    sub.add_parser("test-ws", help="WSga ulanish va HELLO testi")
    sub.add_parser("test-arduino", help="Arduino portini ochish test")
    sub.add_parser("test-scanner", help="Scanner portini ochish test")
    listen_cmd = sub.add_parser("listen-scanner", help="Scanner portidan xom oqimni ko'rsatish")
    listen_cmd.add_argument("--seconds", type=int, default=20)

    # Logs
    logs_cmd = sub.add_parser("logs", help="Xizmat loglarini ko'rsatish")
    logs_cmd.add_argument("--lines", type=int, default=200)

    # Monitor
    sub.add_parser("monitor", help="Interaktiv monitoring (scanner/WS/session)")

    args = parser.parse_args()

    if args.cmd == "setup" or args.cmd is None:
        recreate_venv()
        prompt_config()
        if is_macos():
            ask = input("\nmacOS auto-start xizmati o'rnatilsinmi? [Y/n]: ").strip().lower()
            if ask in ("", "y", "yes"):
                install_service_macos()
        elif is_linux():
            ask = input("\nLinux (systemd) auto-start xizmati o'rnatilsinmi? [Y/n]: ").strip().lower()
            if ask in ("", "y", "yes"):
                install_service_linux()
        else:
            print("OS aniqlanmadi; xizmat o'rnatilmadi.")
    elif args.cmd == "ports":
        ports = list_serial_ports()
        if not ports:
            print("Port topilmadi. Qurilmalarni ulang yoki drayverlarni tekshiring.")
        for p in ports:
            print(p)
    elif args.cmd == "config-show":
        config_show()
    elif args.cmd == "config-edit":
        prompt_config()
    elif args.cmd == "config-set":
        config_set(
            args.arduino_port,
            args.scanner_port,
            args.baudrate,
            args.log_dir,
            args.ws_url,
            args.fandomat_id,
            args.device_token,
            args.version,
        )
    elif args.cmd == "service-install":
        install_service()
    elif args.cmd == "service-remove":
        remove_service()
    elif args.cmd == "service-status":
        service_status()
    elif args.cmd == "service-start":
        service_start()
    elif args.cmd == "service-stop":
        service_stop()
    elif args.cmd == "service-restart":
        service_restart()
    elif args.cmd == "run":
        run_app_foreground()
    elif args.cmd == "test-ws":
        test_ws()
    elif args.cmd == "test-arduino":
        test_serial("arduino")
    elif args.cmd == "test-scanner":
        test_serial("scanner")
    elif args.cmd == "listen-scanner":
        listen_scanner(getattr(args, "seconds", 20))
    elif args.cmd == "logs":
        logs_show(getattr(args, "lines", 200))
    elif args.cmd == "monitor":
        monitor_ui()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
