import os
import subprocess
import sys
from pathlib import Path
import venv

# Constants
CONFIG_FILE = "new.py"
REQUIREMENTS_FILE = "requirements.txt"

# Function to prompt user for input
def prompt_user():
    print("Please provide the following configuration values:")
    ws_url = input("WebSocket URL (default: wss://api.yaxshi.link/ws/fandomats): ") or "wss://api.yaxshi.link/ws/fandomats"
    fandomat_id = input("Fandomat ID (default: 3): ") or "3"
    device_token = input("Device Token (default: fnd_a7b3c9d2e8f4g1h5i6j7k8l9m0n1): ") or "fnd_a7b3c9d2e8f4g1h5i6j7k8l9m0n1"
    version = input("Version (default: 1.0.0): ") or "1.0.0"
    arduino_port = input("Arduino Port (default: /dev/ttyUSB0): ") or "/dev/ttyUSB0"
    scanner_port = input("Scanner Port (default: /dev/ttyACM0): ") or "/dev/ttyACM0"
    baudrate = input("Baudrate (default: 9600): ") or "9600"

    return {
        "WS_URL": ws_url,
        "FANDOMAT_ID": fandomat_id,
        "DEVICE_TOKEN": device_token,
        "VERSION": version,
        "ARDUINO_PORT": arduino_port,
        "SCANNER_PORT": scanner_port,
        "BAUDRATE": baudrate,
    }

# Function to update the configuration file
def update_config_file(config):
    with open(CONFIG_FILE, "r") as file:
        lines = file.readlines()

    with open(CONFIG_FILE, "w") as file:
        for line in lines:
            if line.startswith("WS_URL"):
                file.write(f"WS_URL = \"{config['WS_URL']}\"\n")
            elif line.startswith("FANDOMAT_ID"):
                file.write(f"FANDOMAT_ID = {config['FANDOMAT_ID']}\n")
            elif line.startswith("DEVICE_TOKEN"):
                file.write(f"DEVICE_TOKEN = \"{config['DEVICE_TOKEN']}\"\n")
            elif line.startswith("VERSION"):
                file.write(f"VERSION = \"{config['VERSION']}\"\n")
            elif line.startswith("ARDUINO_PORT"):
                file.write(f"ARDUINO_PORT = \"{config['ARDUINO_PORT']}\"\n")
            elif line.startswith("SCANNER_PORT"):
                file.write(f"SCANNER_PORT = \"{config['SCANNER_PORT']}\"\n")
            elif line.startswith("BAUDRATE"):
                file.write(f"BAUDRATE = {config['BAUDRATE']}\n")
            else:
                file.write(line)

# Function to set up a virtual environment
def setup_virtualenv():
    venv_dir = Path("venv")
    if not venv_dir.exists():
        print("Creating virtual environment...")
        venv.create(venv_dir, with_pip=True)

    python_executable = venv_dir / "bin" / "python"
    print("Installing dependencies...")
    subprocess.run([python_executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE], check=True)

# Function to create a system-wide executable
def create_executable():
    executable_path = Path("/usr/local/bin/yaxshilink-cli")
    script_path = Path(__file__).resolve()

    with open(executable_path, "w") as file:
        file.write(f"#!/bin/bash\n")
        file.write(f"{script_path.parent / 'venv' / 'bin' / 'python'} {script_path} \"$@\"\n")

    os.chmod(executable_path, 0o755)
    print(f"Executable created at {executable_path}")

# Main function
def main():
    config = prompt_user()
    update_config_file(config)
    setup_virtualenv()
    create_executable()
    print("Setup complete. You can now run the program.")

if __name__ == "__main__":
    main()