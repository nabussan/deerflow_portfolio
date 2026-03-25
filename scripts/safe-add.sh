#!/bin/bash
# scripts/safe-add.sh
set -e
PACKAGE="$1"
BACKEND_DIR="$(dirname "$0")/../backend"

if [ -z "$PACKAGE" ]; then
  echo "❌ Kein Paket angegeben. Verwendung: bash scripts/safe-add.sh <paket>[@version]"
  exit 1
fi

cd "$BACKEND_DIR"

echo "🔍 [1/3] pip-audit VOR dem Update..."
uv run pip-audit --progress-spinner off
BEFORE_STATUS=$?

echo "📦 [2/3] Installiere: $PACKAGE"
uv add "$PACKAGE"

echo "🔍 [3/3] pip-audit NACH dem Update..."
uv run pip-audit --progress-spinner off
AFTER_STATUS=$?

if [ $AFTER_STATUS -gt $BEFORE_STATUS ]; then
  echo "⚠️  WARNUNG: Neue Schwachstellen eingeführt!"
  echo "   Rückgängig: git checkout backend/pyproject.toml backend/uv.lock && uv sync"
  exit 1
elif [ $AFTER_STATUS -ne 0 ]; then
  echo "⚠️  Bestehende Schwachstellen vorhanden. $PACKAGE installiert."
else
  echo "✅ Clean. $PACKAGE erfolgreich installiert."
fi
