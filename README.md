# DeerFlow Portfolio – Trading Agent Extension

> **Status: Prototype v0.1.2 – Work in Progress**  
> This is an early-stage prototype. Use at your own risk. Not financial advice.

A fork of [DeerFlow 2.0](https://github.com/bytedance/deer-flow) extended with **live broker connectivity**, **automated portfolio monitoring**, and **Telegram alerts** for individual traders and investors.

---

## Quick Start
```bash
# Clone and install (WSL2/Ubuntu)
git clone https://github.com/nabussan/deerflow_portfolio.git deer-flow
cd deer-flow
git checkout portfolio
bash install.sh
```

📖 Full setup guide: [INSTALL.md](INSTALL.md)
📋 Changelog: [CHANGELOG.md](CHANGELOG.md)
✅ Akzeptanzkriterien: [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md)
🔧 Developer guide: [DEVGUIDE.md](DEVGUIDE.md)
🐛 Troubleshooting: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## What This Adds to DeerFlow

| Feature | Status |
|---|---|
| IBKR Gateway connection (via `ib_insync`) | ✅ v0.1 |
| Persistent connection manager + auto-reconnect | ✅ v0.1 |
| 6 trading tools (account, positions, market data, orders) | ✅ v0.1 |
| Forex rate lookup + currency exchange orders | ✅ v0.1.2 |
| Daily portfolio monitor (08:00 EU / 15:00 US / 21:00 Asia) | ✅ v0.1 |
| Telegram alerts for critical news signals | ✅ v0.1 |
| WSL2 autostart + Windows port-proxy | ✅ v0.1 |
| Weekly position review (Bull/Bear debate) | 🔜 v0.2 |
| Macro indicator tracker | 🔜 v0.2 |
| Alpha Vantage integration | 🔜 v0.2 |
| Options watchlist scanner (IVR, Put-selling candidates) | 🔜 v0.3 |
| Risk manager + position sizing module | 🔜 v0.3 |

---

## Architecture
```
DeerFlow 2.0 (LangGraph + LangChain)
├── backend/src/tools/
│   ├── ibkr_connection.py   ← Persistent IB Gateway connection + Telegram
│   ├── ibkr_tool.py         ← 6 LangChain tools for IBKR
│   └── portfolio_monitor.py ← Scheduled news monitor with LLM analysis
├── scripts/
│   ├── wsl-startup.sh       ← WSL2 autostart script
│   └── windows-portproxy.ps1 ← Windows port-proxy for remote access
└── backend/src/tools/tools.py  ← IBKR tools registered in DeerFlow
```
```
Scheduler (APScheduler)
    → Fetch positions from IBKR Gateway
    → Search news (Tavily)
    → Analyze with Grok 4.1 (xAI)
    → Telegram alert if critical signal detected
```

---

## Server Setup (W541 ThinkPad)

This project runs on a dedicated Windows 10 machine with WSL2:

- **OS:** Windows 10 + WSL2 (Ubuntu 24.04 LTS)
- **Broker:** IB Gateway (Paper/Live, Port 4002)
- **Remote access:** Tailscale + RDP
- **Runtime:** 07:00–24:00 daily
- **UPS:** Marstek Venus E

See [INSTALL.md](INSTALL.md) for full setup instructions.

---

## Prerequisites

- Interactive Brokers account (Paper or Live)
- IB Gateway installed and running (Paper port: 4002)
- Python 3.12+ via `uv`
- Node.js 22+ via `nvm`
- WSL2 (Ubuntu 24.04) on Windows

---

## Configuration

Copy `backend/.env.example` to `backend/.env`:
```env
XAI_API_KEY=           # https://console.x.ai
TAVILY_API_KEY=        # https://tavily.com
TELEGRAM_BOT_TOKEN=    # @BotFather on Telegram
TELEGRAM_CHAT_ID=      # @idbot on Telegram
IBKR_HOST=             # Windows IP from WSL2: ip route | grep default | awk '{print $3}'
IBKR_PORT=4002         # IB Gateway Paper: 4002, Live: 4001
```

---

## Usage

### Chat Interface
Start DeerFlow and ask in chat:
```
"Was ist mein aktueller IBKR Kontostand?"
"Zeige meine offenen Positionen"
"Kaufe 10 Aktien AAPL"
```

### Portfolio Monitor
```bash
cd backend
uv run python3 -c "
from src.tools.portfolio_monitor import run_monitor
run_monitor('US')
"
```

---

## Critical Signal Detection

The portfolio monitor flags positions when detecting:

- **MANAGEMENT** – Negative news about CEO/CFO (resignation, scandal, insider selling)
- **HYPE** – Irrational sentiment (viral X/Twitter, Reddit pump)
- **FUNDAMENTALS** – Revenue decline, shrinking gross margin, negative FCF, guidance cut
- **SECTOR** – Regulatory changes, tariffs, commodity shocks, disruptive competitor

---

## Credits & Acknowledgements

### Built on DeerFlow 2.0
Fork of [DeerFlow 2.0](https://github.com/bytedance/deer-flow) by ByteDance.  
DeerFlow provides the LangGraph-based agent harness, middleware system, frontend, and tool infrastructure.

### Inspired by TradingAgents
Multi-agent architecture concept inspired by [TradingAgents](https://github.com/TauricResearch/TradingAgents) by TauricResearch.  
We plan to adopt the Bull/Bear debate pattern and structured analyst roles in v0.2.

### Key Libraries
- [ib_insync](https://github.com/erdewit/ib_insync) – Interactive Brokers API
- [LangGraph](https://github.com/langchain-ai/langgraph) – Agent orchestration
- [APScheduler](https://github.com/agronholm/apscheduler) – Job scheduling
- [Tailscale](https://tailscale.com) – Secure remote access

---

## Roadmap

### v0.1 (current) ✅
- IBKR Gateway connection + 6 trading tools
- Daily portfolio monitor with Telegram alerts
- W541 server setup (WSL2, autostart, remote access)

### v0.2
- Weekly position review (Bull/Bear debate)
- Macro indicator tracker (CPI, NFP, ISM, Fed)
- Alpha Vantage integration
- Automated port-proxy on WSL2 IP change

### v0.3
- Options watchlist scanner (IVR, Put-selling)
- Position sizing module
- Risk manager agent

---

## Disclaimer

For **research and educational purposes only**.  
Not financial advice. Trading involves significant risk of loss.  
Always verify agent decisions before executing real trades.

---

## License

Inherits [DeerFlow's license](https://github.com/bytedance/deer-flow/blob/main/LICENSE).
