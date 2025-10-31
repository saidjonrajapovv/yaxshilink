#!/usr/bin/env bash
set -euo pipefail

# Simple cross-platform installer for this project.
# - creates a Python virtual environment in .venv
# - installs requirements from requirements.txt (if present)
# - copies config.example.json -> config.json if missing
# - optionally creates and installs a systemd service on Linux

VENV_DIR=".venv"
REQ_FILE="requirements.txt"
EXAMPLE_CONFIG="config.example.json"
CONFIG_FILE="config.json"

info(){ echo "[INFO] $*"; }
err(){ echo "[ERROR] $*" >&2; }

check_command(){
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Required command '$1' not found. Please install it and re-run this script."
    exit 1
  fi
}

OS_NAME=$(uname -s)

check_command python3

# Ensure venv module available
python3 - <<'PY' || {
  echo "python3 venv module missing. On Debian: sudo apt install python3-venv" >&2
  exit 1
}
import venv
PY

if [ ! -d "${VENV_DIR}" ]; then
  info "Creating virtual environment at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
else
  info "Virtual environment already exists at ${VENV_DIR}"
fi

info "Activating virtual environment"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip setuptools wheel

if [ -f "${REQ_FILE}" ]; then
  info "Installing Python requirements from ${REQ_FILE}"
  pip install -r "${REQ_FILE}"
else
  info "No ${REQ_FILE} found. Skipping pip install."
fi

if [ -f "${CONFIG_FILE}" ]; then
  info "${CONFIG_FILE} already exists — leaving it untouched"
else
  if [ -f "${EXAMPLE_CONFIG}" ]; then
    info "Creating ${CONFIG_FILE} from ${EXAMPLE_CONFIG} (edit values as needed)"
    cp "${EXAMPLE_CONFIG}" "${CONFIG_FILE}"
  else
    info "No ${EXAMPLE_CONFIG} found. Creating minimal ${CONFIG_FILE} with defaults"
    cat > "${CONFIG_FILE}" <<EOF
{
  "WS_URL": "wss://api.yaxshi.link/ws/fandomats",
  "FANDOMAT_ID": 3,
  "DEVICE_TOKEN": "REPLACE_ME",
  "VERSION": "1.0.0",
  "ARDUINO_PORT": "/dev/ttyUSB0",
  "SCANNER_PORT": "/dev/ttyACM0",
  "BAUDRATE": 9600,
  "SESSION_TIMEOUT": 90
}
EOF
  fi
fi

echo
if [ "${OS_NAME}" = "Linux" ]; then
  read -rp "Do you want to create & install a systemd service now? (requires sudo) [y/N]: " do_svc
  do_svc=${do_svc:-N}
  if [[ "${do_svc,,}" =~ ^y ]]; then
    mkdir -p deploy
    SERVICE_PATH="deploy/fandomat.service"
    info "Creating service template at ${SERVICE_PATH}"
    cat > "${SERVICE_PATH}" <<SVC
[Unit]
Description=Fandomat Python Service
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
Environment=PYTHONUNBUFFERED=1
ExecStart=$(pwd)/${VENV_DIR}/bin/python $(pwd)/new.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC

    read -rp "Install and enable service to /etc/systemd/system/fandomat.service now? [y/N]: " do_install
    do_install=${do_install:-N}
    if [[ "${do_install,,}" =~ ^y ]]; then
      sudo cp "${SERVICE_PATH}" /etc/systemd/system/fandomat.service
      sudo systemctl daemon-reload
      sudo systemctl enable fandomat.service
      sudo systemctl start fandomat.service
      info "Service installed and started (fandomat.service)"
    else
      info "Service template created at ${SERVICE_PATH}. To enable it later: sudo cp ${SERVICE_PATH} /etc/systemd/system/fandomat.service && sudo systemctl daemon-reload && sudo systemctl enable fandomat.service"
    fi
  fi
else
  info "Detected ${OS_NAME}. Skipping systemd service creation. On macOS you can run the program with: source ${VENV_DIR}/bin/activate && python new.py"
fi

info "Installation complete. To run the program now:"
echo "  source ${VENV_DIR}/bin/activate && python new.py"

deactivate 2>/dev/null || true

exit 0
