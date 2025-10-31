# Raspberry Pi / Debian setup

This repository includes helper scripts to make installing and running the project easier on Raspberry Pi / Debian and other systems.

Quick unified installer

If you want a single, minimal command that prepares a Python virtualenv, installs dependencies, and creates a default `config.json`, use the provided `install.sh`:

```bash
chmod +x install.sh
./install.sh
```

`install.sh` does the following:

- creates a `.venv` Python virtual environment (if missing)
- upgrades pip and installs packages from `requirements.txt` (if present)
- copies `config.example.json` to `config.json` if no `config.json` exists (so you can edit the config before running)
- on Linux it can optionally create and install a `systemd` service template located at `deploy/fandomat.service`

Existing, more detailed Raspberry Pi helper

Files you may also find useful:

- `setup_rpi.sh` — Create a Python virtual environment, install requirements, prompt for configuration and write `config.json`, optionally create and install a `systemd` service.
- `config.example.json` — Example configuration file showing available keys and defaults.
- `deploy/fandomat.service` — Service file template (edit paths and user before installing).

Quick start (on your Raspberry Pi):

1. Make the setup script executable and run it (if you prefer the interactive setup):

```bash
chmod +x setup_rpi.sh
./setup_rpi.sh
```

2. The interactive `setup_rpi.sh` will:

- create a virtual environment in `.venv` (if missing)
- install Python packages from `requirements.txt`
- ask for configuration values and write `config.json`
- optionally create a `deploy/fandomat.service` template and offer to install it

3. If you chose not to install the service automatically, copy the template to `/etc/systemd/system/fandomat.service`, edit `WorkingDirectory` and `ExecStart` to match your project path, then enable:

```bash
sudo cp deploy/fandomat.service /etc/systemd/system/fandomat.service
sudo systemctl daemon-reload
sudo systemctl enable fandomat.service
sudo systemctl start fandomat.service
```

Notes:

- `new.py` will use `config.json` if present, or environment variables. This makes it flexible for service installs.
- The scripts attempt to be safe on non-Linux systems — they will not try to install systemd services on macOS unless explicitly requested.
