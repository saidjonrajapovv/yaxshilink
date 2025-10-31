# YaxshiLink Fandomat

This README explains how to run the Fandomat device software (`new.py`), create a virtual environment, install dependencies, and run the program.

Requirements

- Python 3.10+ recommended
- A system with access to Arduino and scanner serial devices

Setup (recommended)

1. Create and activate a virtual environment (macOS / Linux):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Edit configuration in `new.py` or use your own tool to inject configuration values. The important constants are at the top of `new.py`:

- `WS_URL` - websocket endpoint
- `FANDOMAT_ID`, `DEVICE_TOKEN`, `VERSION`
- `ARDUINO_PORT`, `SCANNER_PORT`, `BAUDRATE`

The program will create a `logs/` directory and write logs there.

Run

```bash
# with venv activated
python new.py
```

Notes & behavior

- The app connects to the WebSocket and sends a `HELLO` message to authenticate.
- It responds to `PING` messages with `PONG`.
- On `START_SESSION` the device opens the acceptor (sends `S` to Arduino), and sends `SESSION_STARTED` back.
- On barcode scans it sends `CHECK_BOTTLE` to the server and reacts accordingly to `BOTTLE_CHECK_RESULT`.
- On inactivity (`SESSION_TIMEOUT`, default 90s) it closes the session and reports `SESSION_END`.
- The code uses exponential backoff when reconnecting to the server.

Troubleshooting

- If serial ports fail to open, confirm device paths and permissions.
- If you get permission errors for `/usr/local/bin` when installing CLI tools, either run with `sudo` or place executables under `~/.local/bin`.

If you want, I can also add a small CLI to set the constants into `new.py` and create a system launcher.
