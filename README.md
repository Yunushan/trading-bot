# Binance Trading Bot

A PyQt6 desktop GUI for spot and futures trading on Binance.

## Requirements
- Python 3.10+ (3.11 or 3.12 recommended)
- pip
- Internet access for the Binance API

---

## Install Python + dependencies

### Windows
1. Install Python from https://python.org (check **Add Python to PATH** during setup).
2. Open **PowerShell**:
   ```powershell
   python -m pip install --upgrade pip
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Run:
   ```powershell
   python main.py
   ```

### Linux (Debian/Ubuntu/Fedora/Arch)
```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### macOS (Intel & Apple Silicon)
```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

If you see issues with PyQt on macOS, install the Qt runtime:
```bash
pip install PyQt6 PyQt6-Qt6
```

### FreeBSD
```sh
pkg install python3 py39-pip  # or pkg install python311 py311-pip
python3 -m pip install --upgrade pip
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

---

## Usage
- Paste your **API Key/Secret**.
- Select **Account Type** (Spot/Futures) and **Mode** (Live/Testnet).
- Choose symbols and intervals, set indicators and position %.
- Press **Start**.
- The **Positions** tab shows each interval separately with **Size**, **Margin Ratio**, **Margin**, **PNL (ROI%)**, **Entry TF**, **Side**, **Time**, **Status**, and **Close**.

### Safe Exit
Closing the window or pressing Alt+F4 will market-close all active positions (best effort).

## License
MIT
