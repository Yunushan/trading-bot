# MetaTrader 4 bridge

The MT4 bridge supports the currently verified MT4-only broker routes for Trade Nation, FXTF, and FOREX EXCHANGE. It consists of:

- `Languages/Python/app/integrations/brokers/metatrader4_bridge.py`: authenticated command host and Python connector.
- `Languages/MQL4/Experts/TradingBotBridge.mq4`: companion Expert Advisor that executes inside an MT4 terminal.

The Python connector and the Expert Advisor each have an independent live-order gate. A passed per-broker account evidence artifact is still required before claiming official live support.

## Local setup

1. Compile `TradingBotBridge.mq4` in the MT4 MetaEditor and attach it to one chart in the intended account.
2. In MT4, add `http://127.0.0.1:8765` under **Tools > Options > Expert Advisors > Allow WebRequest for listed URL**.
3. Set a shared token of at least 16 characters and start the bridge:

   ```powershell
   $env:TRADING_BOT_MT4_BRIDGE_TOKEN = "replace-with-a-long-random-token"
   trading-bot-mt4-bridge --host 127.0.0.1 --port 8765
   ```

4. Configure the EA with the same `BridgeBaseUrl`, `BridgeToken`, and a unique `TerminalId`. Leave `EnableLiveOrders=false` until reads and dry runs have been verified.
5. Configure the Python connector with the same values:

   ```python
   from app.integrations.brokers import MetaTrader4BridgeConnector

   connector = MetaTrader4BridgeConnector(
       provider="Trade Nation",
       terminal_id="trade-nation-demo",
       token="replace-with-a-long-random-token",
       bridge_url="http://127.0.0.1:8765",
   )

   account = connector.fetch_account_snapshot()
   preview = connector.submit_market_order(
       symbol="EURUSD",
       side="buy",
       volume=0.01,
   )
   ```

Live submission additionally requires `dry_run=False`, `allow_live=True`, and `EnableLiveOrders=true` in the EA.

## Remote setup

Direct non-loopback bridge binding requires a TLS certificate and key:

```powershell
trading-bot-mt4-bridge --host 0.0.0.0 --port 8765 --certfile server.crt --keyfile server.key --advertised-host bridge.example.com
```

Use the resulting `https://` URL in both the connector and MT4 WebRequest allow-list. A bridge bound to loopback may also be published through an authenticated TLS reverse proxy. Plain HTTP remote URLs are rejected by default.

## Safety properties

- Every endpoint requires `X-MT4-Bridge-Token`; tokens are never returned in snapshots or logs.
- The server bounds tokens, command bodies, form fields, queue growth, error messages, and connector timing values; it validates terminal ownership and leases one command at a time.
- The EA rejects unsafe bridge URLs before sending its token: loopback HTTP is allowed for local use, while remote URLs must use HTTPS; URL credentials, query strings, fragments, and invalid ports are rejected.
- The EA bounds the bridge token, terminal identifier, polling interval, and request timeout before it creates its receipt file or starts polling.
- The Python connector does not enqueue an order, cancellation, or close unless `allow_live=True`.
- The EA refuses every mutation unless `EnableLiveOrders=true`.
- Before a mutation, the EA persists an ambiguity receipt in the MT4 common files directory. It replaces that receipt with the final result after execution. Redelivery replays the receipt rather than the order, preventing duplicate execution after a lost HTTP acknowledgement.
- A crash between receipt creation and result persistence produces an explicit ambiguous-outcome failure that must be reconciled against the MT4 account.

## Protocol

The version 1 protocol exposes token-authenticated health, enqueue, status, agent-poll, and agent-result endpoints under `/v1`. Connector payloads use JSON. The EA poll/result surface uses standard form encoding so it does not depend on a third-party MQL4 JSON parser; result payloads are JSON carried in the `payload_json` form field.

Supported operations are account snapshot, market snapshot, open positions, open pending orders, market order, pending-order cancellation, and position close.
