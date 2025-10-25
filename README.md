# Multilingual Trading Bot Workspace

This repository now organizes every implementation by **language** and **exchange** so each stack can evolve independently while sharing research assets. The existing production-ready GUI bot lives under the Python/Crypto-Exchanges/Binance lane, and additional ports (C++23, C, Rust, …) will grow beside it.

## Directory layout

```
Languages/
|- Python/
|  |- Crypto-Exchanges/   # language-scoped exchange folders (Binance, Bybit, …)
|  |  \- Binance/         # full PyQt6 application (migrated from the repo root)
|  \- ForexBrokers/       # language-scoped FX broker folders (FXCM, …)
|- C++23/
|  \- backtest_tab/       # Qt/C++23 prototype of the Backtest tab UI
|- C/
\- Rust/
```

## Running the Python/Crypto-Exchanges/Binance app

```powershell
cd Languages/Python/Crypto-Exchanges/Binance
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r ..\..\..\..\requirements.txt
python main.py
```

Or double-click `Languages/Python/Crypto-Exchanges/Binance/Binance-Bot-Trading.bat` on Windows for the guided setup.

Want the guided language/market wizard? From the repo root run:

```powershell
python starter.py
```

## Next steps

- Add additional exchange/broker folders per language as needed.
- Continue porting UI/logic layers (e.g., the new Qt/C++23 backtest tab lives under `Languages/C++23/backtest_tab`).
- Share common assets (docs, strategy specs) through subfolders under each language to keep responsibilities isolated.
