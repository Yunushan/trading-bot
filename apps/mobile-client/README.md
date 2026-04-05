# Trading Bot Mobile Client

Thin Expo-based native Android/iOS client over the existing Trading Bot service API.

## Scope

This client is intentionally small:

- connect to the headless service API
- inspect runtime, status, backtest state, and recent logs
- request bot start/stop
- trigger the extracted service-owned backtest runner

It does **not** run trading logic locally, and it should never store exchange or broker credentials on the phone.

## Install

From this folder:

```bash
npm install
```

Start the Expo dev server:

```bash
npm run start
```

Open directly on Android or iOS:

```bash
npm run android
npm run ios
```

Optional native cloud/local build profiles are defined in:

```text
eas.json
```

## Connect to the backend

If you run this on a physical phone, do not use `127.0.0.1` unless the backend is also on the phone.
Point the app at the LAN IP of the machine running:

```bash
python ../service-api/main.py --serve --host 0.0.0.0 --port 8000
```

Example:

```text
http://192.168.1.25:8000
```

If the backend is protected, enter the same bearer token used by `BOT_SERVICE_API_TOKEN`.

## Notes

- This is a thin-client scaffold, not a full production mobile app.
- It shares the same backend contract as the web dashboard.
- Future work should add richer config editing, positions, and chart views without moving trading execution onto the device.
