# Raspberry Pi / Debian setup

This repository includes a helper script to make installing and running the project on Raspberry Pi OS easier.

Files added:

- `setup_rpi.sh` — Create a Python virtual environment, install requirements, prompt for configuration and write `config.json`, optionally create and install a `systemd` service.
- `config.example.json` — Example configuration file showing available keys and defaults.
- `deploy/fandomat.service` — Service file template (edit paths and user before installing).

Quick start (on your Raspberry Pi):

1. Make the setup script executable and run it:

```bash
chmod +x setup_rpi.sh
./setup_rpi.sh
```

2. The script will:

- create a virtual environment in `.venv` (if missing)
- install Python packages from `requirements.txt`
- ask for configuration values and write `config.json`
- optionally create a `deploy/fandomat.service` template and offer to install it

3. If you chose not to install service automatically, copy the template to `/etc/systemd/system/fandomat.service`, edit `WorkingDirectory` and `ExecStart` to match your project path, then enable:

```bash
sudo cp deploy/fandomat.service /etc/systemd/system/fandomat.service
sudo systemctl daemon-reload
sudo systemctl enable fandomat.service
sudo systemctl start fandomat.service
```

Notes:

- `new.py` will use `config.json` if present, or environment variables. This makes it flexible for service installs.
- The script attempts to be safe on non-Linux systems — it will not try to install systemd services on macOS.
