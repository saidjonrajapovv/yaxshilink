#!/usr/bin/env bash
set -euo pipefail

# Installer for Raspberry Pi (Debian-based)
# - Creates venv under /opt/yaxshilink
# - Installs this project
# - Runs setup wizard to create config
# - Installs and enables systemd service

PREFIX=${PREFIX:-/opt/yaxshilink}
VENV="$PREFIX/.venv"
SERVICE_NAME=yaxshilink.service
CONFIG_PATH=/etc/yaxshilink/config.json

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "This installer must be run as root (sudo)." >&2
    exit 1
  fi
}

require_root

echo "Creating install dir: $PREFIX"
mkdir -p "$PREFIX"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install it and retry." >&2
  exit 1
fi

echo "Creating virtualenv: $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip

echo "Installing package into venv"
"$VENV/bin/pip" install .

echo "Running setup wizard to create config at $CONFIG_PATH"
"$VENV/bin/yaxshilink-setup"

if [ ! -f "$CONFIG_PATH" ]; then
  echo "Config not found at $CONFIG_PATH. Installation cannot continue." >&2
  echo "Re-run: $VENV/bin/yaxshilink-setup and then re-run this installer." >&2
  exit 1
fi

echo "Writing systemd unit: /etc/systemd/system/$SERVICE_NAME"
cat >/etc/systemd/system/$SERVICE_NAME <<EOF
[Unit]
Description=YaxshiLink Device Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
Environment=YAXSHILINK_CONFIG=$CONFIG_PATH
ExecStart=$VENV/bin/yaxshilink
Restart=always
RestartSec=2
User=root
WorkingDirectory=$PREFIX
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd and enabling service"
systemctl daemon-reload
systemctl enable --now $SERVICE_NAME

echo "Installation complete. Check status with: systemctl status $SERVICE_NAME"
