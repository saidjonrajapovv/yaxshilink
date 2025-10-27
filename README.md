# YaxshiLink service

Raspberry Pi service for integrating a barcode scanner and Arduino with your backend via WebSocket and HTTP API.

## What it does

- Connects to two serial devices:
  - Arduino (controls actuators via simple commands P/A/R/S/E)
  - USB Scanner (reads barcodes)
- Maintains a WebSocket connection to your server to manage sessions
- Validates scanned SKUs via HTTP API and logs results
- Runs as a systemd service and restarts automatically

## Configure

Run the interactive setup to create a config file:

```
yaxshilink-setup
```

It will ask for:

- Server host:port, e.g. `10.10.3.49:8000`
- Device number/UUID
- Arduino serial port (pick from `/dev/serial/by-id/*` if available)
- Scanner serial port
- Baudrate (default 9600)

By default, the config is saved to `/etc/yaxshilink/config.json` (root) or `~/.config/yaxshilink/config.json`.

You can also override via environment variables:

- `YAX_BASE_IP`
- `YAX_DEVICE_NUMBER`
- `YAX_ARDUINO_PORT`
- `YAX_SCANNER_PORT`
- `YAX_BAUDRATE`
- `YAX_LOG_DIR`

## Install on Raspberry Pi (as service)

If you have this repo on the device, run the installer as root:

```
sudo bash scripts/install.sh
```

This will:

- Create a venv in `/opt/yaxshilink/.venv`
- Install this package into the venv
- Run the setup wizard and save `/etc/yaxshilink/config.json`
- Create and enable the `yaxshilink.service`

Check service status:

```
systemctl status yaxshilink.service
journalctl -u yaxshilink.service -f
```

## Logs

Logs are written to one of:

- `/var/log/yaxshilink` (if writable)
- `~/.local/state/yaxshilink/logs`
- `./logs` (current directory)

## Development

Run locally from source:

```
python -m yaxshilink.app
```

Or via entrypoint after `pip install -e .`:

```
yaxshilink
```

## Notes

- For stable serial device names, prefer `/dev/serial/by-id/*` over `/dev/ttyUSB*`.
- Ensure the user running the service has permission to access serial devices (typically belongs to the `dialout` group), or run as root (default in the provided unit).
