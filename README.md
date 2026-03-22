# DeerFlow Portfolio – Trading Agent Extension

> **Status: Prototype v0.1 – Work in Progress**  
> This is an early-stage prototype. Use at your own risk. Not financial advice.

A fork of [DeerFlow 2.0](https://github.com/bytedance/deer-flow) extended with **live broker connectivity**, **automated portfolio monitoring**, and **Telegram alerts** for individual traders and investors.

---

## What This Adds to DeerFlow

| Feature | Status |
|---|---|
| IBKR Gateway connection (via `ib_insync`) | ✅ v0.1 |
| Persistent connection manager + auto-reconnect | ✅ v0.1 |
| 6 trading tools (account, positions, market data, orders) | ✅ v0.1 |
| Daily portfolio monitor (08:00 EU / 15:00 US / 21:00 Asia) | ✅ v0.1 |
| Telegram alerts for critical news signals | ✅ v0.1 |
| Weekly position review (Bull/Bear debate) | 🔜 v0.2 |
| Macro indicator tracker | 🔜 v0.2 |
| Options watchlist scanner (IVR, Put-selling candidates) | 🔜 v0.3 |
| Risk manager + position sizing module | 🔜 v0.3 |
| Alpha Vantage integration | 🔜 v0.2 |

---

## Architecture

\`\`\`
DeerFlow 2.0 (LangGraph + LangChain)
├── backend/src/tools/
│   ├── ibkr_connection.py   ← Persistent IB Gateway connection + Telegram
│   ├── ibkr_tool.py         ← 6 LangChain tools for IBKR
│   └── portfolio_monitor.py ← Scheduled news monitor with LLM analysis
└── backend/src/tools/tools.py  ← IBKR tools registered in DeerFlow
\`\`\`

\`\`\`
Scheduler (APScheduler)
    → Fetch positions from IBKR Gateway
    → Search news (Tavily)
    → Analyze with Grok 4.1 (xAI)
    → Telegram alert if critical signal detected
\`\`\`

---

## Prerequisites

- [DeerFlow 2.0](https://github.com/bytedance/deer-flow) base installation
- Interactive Brokers account (Paper or Live)
- IB Gateway installed and running (Paper port: 4002)
- Python 3.12+ via \`uv\`
- WSL2 (Ubuntu 24) recommended for Windows users

---

## Installation

\`\`\`bash
# 1. Clone this repo
git clone https://github.com/nabussan/deerflow_portfolio.git
cd deerflow_portfolio

# 2. Install additional dependencies
cd backend
uv add ib_insync apscheduler

# 3. Configure environment
cp backend/.env.example backend/.env
# Edit .env with your API keys

# 4. Start DeerFlow
./start.sh
\`\`\`

---

## Configuration

Copy \`backend/.env.example\` to \`backend/.env\` and fill in:

\`\`\`env
# LLM
XAI_API_KEY=your_grok_key

# Broker
IBKR_HOST=172.18.240.1   # Windows IP from WSL2 (ip route | grep default)
IBKR_PORT=4002            # IB Gateway Paper: 4002, Live: 4001

# News
TAVILY_API_KEY=your_tavily_key

# Alerts
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Optional
GOOGLE_API_KEY=your_gemini_key
ALPHA_VANTAGE_API_KEY=your_av_key
\`\`\`

---

## Usage

### Chat Interface
Start DeerFlow and ask in the chat:
\`\`\`
"Was ist mein aktueller IBKR Kontostand?"
"Zeige meine offenen Positionen"
"Kaufe 10 Aktien AAPL"
\`\`\`

### Portfolio Monitor (manual test)
\`\`\`bash
cd backend
uv run python3 -c "
from src.tools.portfolio_monitor import run_monitor
run_monitor('US')   # or 'EU' or 'ASIA'
"
\`\`\`

### Portfolio Monitor (scheduled)
\`\`\`bash
cd backend
uv run python3 -m src.tools.portfolio_monitor
# Runs daily: 08:00 EU, 15:00 US, 21:00 Asia (Europe/Berlin)
\`\`\`

---

## Critical Signal Detection

The portfolio monitor flags positions when it detects:

- **MANAGEMENT** – Negative news about CEO/CFO (resignation, scandal, insider selling)
- **HYPE** – Irrational sentiment signals (viral X/Twitter, Reddit pump)
- **FUNDAMENTALS** – Revenue decline, shrinking gross margin, negative FCF, guidance cut
- **SECTOR** – Regulatory changes, tariffs, commodity shocks, disruptive competitor news

---

## Credits & Acknowledgements

### Built on DeerFlow 2.0
This project is a fork of [DeerFlow 2.0](https://github.com/bytedance/deer-flow) by ByteDance.
DeerFlow provides the LangGraph-based agent harness, middleware system, frontend, and tool infrastructure that powers this project.
We are deeply grateful to the ByteDance DeerFlow team for open-sourcing their work.

### Inspired by TradingAgents
The multi-agent architecture concept – specialized analyst roles, Bull/Bear researcher debates, and the risk management layer (planned for v0.3) – is inspired by [TradingAgents](https://github.com/TauricResearch/TradingAgents) by TauricResearch.

Specifically, we plan to adopt:
- The **dual-model strategy** (deep-thinking models for analysis, fast models for data retrieval)
- The **Bull/Bear debate pattern** for weekly position reviews
- The **structured analyst roles** (News, Fundamentals, Sentiment, Technical)

We do not use TradingAgents code directly. Our implementation is original, built natively on DeerFlow's tool and middleware system.

### Key Libraries
- [ib_insync](https://github.com/erdewit/ib_insync) – Interactive Brokers API wrapper
- [LangGraph](https://github.com/langchain-ai/langgraph) – Agent orchestration
- [LangChain](https://github.com/langchain-ai/langchain) – LLM integration
- [APScheduler](https://github.com/agronholm/apscheduler) – Job scheduling
- [Tavily](https://tavily.com) – AI-optimized web search

---

## Roadmap

### v0.1 (current)
- IBKR Gateway connection
- 6 trading tools in DeerFlow chat
- Daily portfolio monitor with Telegram alerts

### v0.2
- Weekly position review (Bull/Bear debate)
- Macro indicator tracker (CPI, NFP, ISM, Fed)
- Alpha Vantage integration
- W541 server setup guide

### v0.3
- Options watchlist scanner (IVR, Put-selling candidates)
- Position sizing module
- Risk manager agent

---

## Disclaimer

This project is for **research and educational purposes only**.
It is not financial advice. Trading involves significant risk of loss.
Always verify agent decisions before executing real trades.
The authors are not responsible for any financial losses.

---

## License

This project inherits [DeerFlow's license](https://github.com/bytedance/deer-flow/blob/main/LICENSE).
Our extensions are released under the same terms.
