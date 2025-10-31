#!/usr/bin/env bash
set -euo pipefail

# Raspberry Pi / Debian-friendly setup script
# - creates a Python virtual environment
# - installs requirements
# - prompts for global variables and writes config.json
# - optionally outputs a systemd service file and (optionally) installs it

VENV_DIR=".venv"
REQ_FILE="requirements.txt"
CONFIG_FILE="config.json"

DEFAULT_WS_URL="wss://api.yaxshi.link/ws/fandomats"
DEFAULT_FANDOMAT_ID="3"
DEFAULT_DEVICE_TOKEN="fnd_a7b3c9d2e8f4g1h5i6j7k8l9m0n1"
DEFAULT_VERSION="1.0.0"
DEFAULT_ARDUINO_PORT="/dev/ttyUSB0"
DEFAULT_SCANNER_PORT="/dev/ttyACM0"
DEFAULT_BAUDRATE="9600"
DEFAULT_SESSION_TIMEOUT="90"

info(){ echo "[INFO] $*"; }
err(){ echo "[ERROR] $*" >&2; }

check_command(){
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Required command '$1' not found. Please install it and re-run this script."
    exit 1
  fi
}

check_command python3

# Ensure venv module available
python3 - <<'PY' || {
  echo "python3 venv module missing. On Debian: sudo apt install python3-venv" >&2
  exit 1
}
import venv
PY

info "Creating virtual environment at ${VENV_DIR} (if missing)"
if [ ! -d "${VENV_DIR}" ]; then
  python3 -m venv "${VENV_DIR}"
fi

info "Activating virtual environment and upgrading pip"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip setuptools wheel

if [ -f "${REQ_FILE}" ]; then
  info "Installing Python requirements from ${REQ_FILE}"
  pip install -r "${REQ_FILE}"
else
  info "No ${REQ_FILE} found. Skipping pip install." 
fi

prompt(){
  local varname="$1"; shift
  local default="$1"; shift
  local val
  read -rp "$varname [$default]: " val
  echo "${val:-$default}"
}

info "Please enter global configuration values. Press ENTER to accept defaults."
WS_URL=$(prompt "WS_URL" "$DEFAULT_WS_URL")
FANDOMAT_ID=$(prompt "FANDOMAT_ID" "$DEFAULT_FANDOMAT_ID")
DEVICE_TOKEN=$(prompt "DEVICE_TOKEN" "$DEFAULT_DEVICE_TOKEN")
VERSION=$(prompt "VERSION" "$DEFAULT_VERSION")
ARDUINO_PORT=$(prompt "ARDUINO_PORT" "$DEFAULT_ARDUINO_PORT")
SCANNER_PORT=$(prompt "SCANNER_PORT" "$DEFAULT_SCANNER_PORT")
BAUDRATE=$(prompt "BAUDRATE" "$DEFAULT_BAUDRATE")
SESSION_TIMEOUT=$(prompt "SESSION_TIMEOUT" "$DEFAULT_SESSION_TIMEOUT")

cat > "${CONFIG_FILE}" <<EOF
{
  "WS_URL": "${WS_URL}",
  "FANDOMAT_ID": ${FANDOMAT_ID},
  "DEVICE_TOKEN": "${DEVICE_TOKEN}",
  "VERSION": "${VERSION}",
  "ARDUINO_PORT": "${ARDUINO_PORT}",
  "SCANNER_PORT": "${SCANNER_PORT}",
  "BAUDRATE": ${BAUDRATE},
  "SESSION_TIMEOUT": ${SESSION_TIMEOUT}
}
EOF

info "Wrote configuration to ${CONFIG_FILE}"

echo
read -rp "Do you want to create a systemd service file for automatic start on boot? [y/N]: " install_svc
install_svc=${install_svc:-N}
if [[ "${install_svc,,}" =~ ^y ]]; then
  SERVICE_PATH="deploy/fandomat.service"
  mkdir -p deploy
  cat > "${SERVICE_PATH}" <<SVC
[Unit]
Description=Fandomat Python Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=$(pwd)
Environment=PYTHONUNBUFFERED=1
ExecStart=$(pwd)/${VENV_DIR}/bin/python $(pwd)/new.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC

  info "Created service template at ${SERVICE_PATH}"

  if [ "$(uname -s)" = "Linux" ]; then
    echo
    read -rp "Install the service to /etc/systemd/system/ and enable it now? (requires sudo) [y/N]: " do_install
    do_install=${do_install:-N}
    if [[ "${do_install,,}" =~ ^y ]]; then
      sudo cp "${SERVICE_PATH}" /etc/systemd/system/fandomat.service
      sudo systemctl daemon-reload
      sudo systemctl enable fandomat.service
      sudo systemctl start fandomat.service
      info "Service installed and started (fandomat.service)"
    else
      info "To enable later: sudo cp ${SERVICE_PATH} /etc/systemd/system/fandomat.service && sudo systemctl daemon-reload && sudo systemctl enable fandomat.service"
    fi
  else
    info "Detected non-Linux OS. Skipping automatic service install. Copy '${SERVICE_PATH}' to /etc/systemd/system/ on your Pi and enable it there."
  fi
else
  info "Skipping service creation. You can create one using 'deploy/fandomat.service' as a template."
fi

info "Setup complete. To run the program now:"
echo "  source ${VENV_DIR}/bin/activate && python new.py"

deactivate 2>/dev/null || true

exit 0
