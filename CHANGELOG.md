# Changelog

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
