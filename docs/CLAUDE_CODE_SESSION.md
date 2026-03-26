# Claude Code Session wiederherstellen

---

## Von P53 (Laptop) aus

### 1. Verbindung zu W541 herstellen

**Option A – VS Code Remote SSH:**
```
F1 → "Remote-SSH: Connect to Host" → w541
```
Dann Terminal öffnen (`Ctrl+J`).

**Option B – direktes SSH:**
```bash
ssh deerflow@100.88.180.28
```

### 2. Claude Code starten

```bash
cd ~/deer-flow
claude
```

Das war's. Claude Code öffnet sich im Projektkontext mit dem bestehenden Memory.

---

## Direkt auf W541 (lokal)

WSL2-Terminal öffnen (Windows-Taste → "Ubuntu"), dann:

```bash
cd ~/deer-flow
claude
```

---

## Falls `claude` nicht gefunden wird

```bash
export PATH="$HOME/.local/bin:$PATH"
cd ~/deer-flow
claude
```

Dauerhaft fixen (einmalig):
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## Hinweise

- Claude Code startet immer im aktuellen Verzeichnis als Projektkontext — daher immer zuerst `cd ~/deer-flow`
- Memory (frühere Sessions) wird automatisch geladen
- Laufende Services müssen **nicht** neu gestartet werden — Claude Code ist unabhängig von DeerFlow
