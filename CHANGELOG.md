# Changelog

## [0.1.2] - 2026-03-25

### Added
- **Forex Trading**: `get_forex_rate(pair)` – Bid/Ask/Mid für beliebige Währungspaare (EURUSD, GBPUSD, USDJPY …)
- **Forex Trading**: `place_forex_order(pair, action, quantity, order_type, limit_price)` – Market- und Limit-Orders via IBKR IDEALPRO; Menge in der Basiswährung (z.B. 10 000 EUR bei EURUSD)
- Alle 8 IBKR-Tools in `config.yaml` unter Tool-Gruppe `ibkr` registriert

### Fixed
- **„There is no current event loop in thread"** (`RuntimeError` in Python 3.12): `ib_insync`'s `Client.sendMsg()` ruft intern `asyncio.get_event_loop()` auf, das im LangGraph-Thread-Pool wirft. Fix: `reqMktData()`, `placeOrder()` und `cancelOrder()` laufen jetzt als `async`-Wrapper über `ibkr_submit()` auf dem dedizierten `ibkr-loop`-Thread.
- **xAI/Grok 400 „Each message must have at least one content element"**: `AIMessage` nach Tool-Call hat leeres `content`-Feld, das xAI ablehnt. Fix in `DanglingToolCallMiddleware._fix_empty_ai_content()`: leerer Content wird vor dem Model-Call durch ein Leerzeichen ersetzt.
- **IBKR-Tools nicht erreichbar**: Tools waren implementiert, aber nicht in `config.yaml` eingetragen → Agent kannte sie nicht. Behoben durch explizite Registrierung aller 8 Tools.

### Tests
- 9 neue Unit-Tests für `get_forex_rate` und `place_forex_order` (SK-08/SK-09)
- Test-Fixture `patch_validate` in `test_ibkr_tools.py` erweitert: Wrapper-Coroutinen (`_req`, `_place`, `_cancel`) werden auf frischem Event-Loop ausgeführt; `sleep`- und `*Async`-Coroutinen werden ohne Ausführung geschlossen


## [0.1.1] - 2026-03-25

### Security
- Added `pip-audit` as dev dependency
- Fixed CVE-2025-67221: `orjson` 3.11.5 → 3.11.6
- Fixed CVE-2026-30922: `pyasn1` 0.6.2 → 0.6.3
- Fixed CVE-2026-32597: `pyjwt` 2.10.1 → 2.12.0
- Added `scripts/safe-add.sh`: pip-audit wrapper for `uv add`
- Not affected by LiteLLM TeamPCP supply chain attack (2026-03-24)

### Known Open CVEs
- `pygments` 2.19.2 (CVE-2026-4539): no fix available yet, transitive dependency only


## [0.1.1] - 2026-03-23

### Added
- `backend/src/tools/logger.py` – Centralized logging (RotatingFileHandler, 5 MB / 3 backups)
- Structured logging in `portfolio_monitor.py` – start/end, positions, signals, Telegram, tracebacks
- Structured logging in `ibkr_connection.py` – connection events, mode, reconnects
- Paper/Live safety guard in `ibkr_connection.py` – live mode requires `IBKR_MODE=live` + `IBKR_PORT=4001` + `IBKR_LIVE_CONFIRMED=true`
- `scripts/restart.sh` – one-command restart with startup logging
- `DEVGUIDE.md` – Tailscale setup, dev→prod workflow, logging reference, component map

### Changed
- `backend/.env.example` – added `IBKR_MODE` and `IBKR_LIVE_CONFIRMED` variables

## [0.1.0] - 2026-03-23

### Added
- IBKR Gateway connection via `ib_insync` (persistent, auto-reconnect)
- 6 LangChain trading tools: `get_account_info`, `get_positions`, `get_market_data`, `place_order`, `get_open_orders`, `cancel_order`
- Portfolio Monitor: daily news scan (08:00 EU / 15:00 US / 21:00 Asia)
- Critical signal detection: Management, Hype, Fundamentals, Sector
- Telegram alerts for critical portfolio signals
- Weekly IB Gateway reconnect notification via Telegram
- WSL2 autostart via `/etc/wsl.conf`
- Windows port-proxy script + scheduled task for remote access
- Tailscale integration for secure remote access
- `install.sh` for automated WSL2 setup
- `INSTALL.md` with full setup guide

### Infrastructure
- W541 ThinkPad as dedicated server (Windows 10, WSL2, Ubuntu 24.04)
- IB Gateway (Paper Account, Port 4002)
- DeerFlow 2.0 + LangGraph + Grok 4.1 Fast (xAI)
- Telegram Bot for alerts

### Known Issues
- WSL2-IP changes on reboot → port-proxy script runs automatically via Task Scheduler
- IB Gateway weekly forced disconnect (Saturday night) → manual re-login required (~1 min)

### Roadmap → v0.2
- Weekly position review (Bull/Bear debate)
- Macro indicator tracker (CPI, NFP, ISM, Fed)
- Alpha Vantage integration
- Automated port-proxy on WSL2 IP change
