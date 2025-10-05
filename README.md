<p style="color:#b71c1c; font-weight:bold; text-align:center;">
  WARNING: Binance Trading Bot is still in BETA. It may contain mistakes, bugs, or errors.
</p>
<p style="color:#b71c1c; text-align:center;">
  Neither the author nor this bot accepts any legal responsibility for trading outcomes. Use it at your own risk.
</p>

# Binance Trading Bot

A PyQt6 desktop GUI for spot and futures trading on Binance.

## Introduction

This repository provides a desktop assistant for building and exercising trading strategies on Binance. The application focuses on transparency and configurability, yet it is an experimental project that should be evaluated carefully on demo accounts before live deployment. Attachments such as hero banners or platform-specific previews can help you showcase the bot inside documentation or release notes.



---

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

---

## License

Copyright (c) 2025 Binance Trading Bot contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


