# Security Policy

## Supported Versions
Use the latest version on the `portfolio` branch.

## Reporting a Vulnerability
https://github.com/bytedance/deer-flow/security

---

## Dependency Security

### Tooling
```bash
cd backend && uv run pip-audit
```

### Safe Dependency Updates
```bash
bash scripts/safe-add.sh <package>[@version]
```

### Weekly Automated Audit (Telegram)
Add to crontab (`crontab -e`):
```cron
0 8 * * 1 cd /home/deerflow/deer-flow/backend && uv run pip-audit --progress-spinner off 2>&1 | grep -q "No known vulnerabilities" || curl -s -X POST "https://api.telegram.org/bot$(grep TELEGRAM_BOT_TOKEN .env | cut -d= -f2)/sendMessage" -d "chat_id=$(grep TELEGRAM_CHAT_ID .env | cut -d= -f2)&text=⚠️ pip-audit: Schwachstelle gefunden! cd ~/deer-flow/backend && uv run pip-audit"
```

### Known Open CVEs
| Package | Version | CVE | Fix | Notes |
|---------|---------|-----|-----|-------|
| `pygments` | 2.19.2 | CVE-2026-4539 | – | Transitive dependency only. No fix available yet. |

### Supply Chain Incident History
| Date | Incident | Impact | Action |
|------|----------|--------|--------|
| 2026-03-24 | LiteLLM 1.82.7/1.82.8 (TeamPCP) | **Not affected** | Verified via `uv pip list` |

### General Principles
- Pin versions in `pyproject.toml`
- Never run `uv add` without `scripts/safe-add.sh`
- Treat `.env` as high-value target – rotate on suspected compromise
- Credentials at risk: `XAI_API_KEY`, `TAVILY_API_KEY`, `TELEGRAM_BOT_TOKEN`, IBKR
- Always commit `backend/uv.lock` after updates
