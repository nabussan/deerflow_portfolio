#!/bin/bash
echo "Starting DeerFlow..."

# LangGraph Backend
cd /home/python/deer-flow/backend
uv run langgraph dev --port 2024 --no-browser --allow-blocking > /tmp/langgraph.log 2>&1 &uv run langgraph dev --port 2024 --no-browser --allow-blocking > /tmp/langgraph.log 2>&1 &
echo "LangGraph PID: $!"

sleep 5

# Gateway
uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001 > /tmp/gateway.log 2>&1 &
echo "Gateway PID: $!"

sleep 3

# Frontend
cd /home/python/deer-flow/frontend
pnpm dev > /tmp/frontend.log 2>&1 &
echo "Frontend PID: $!"

sleep 5

echo ""
echo "✅ All services started!"
echo "📺 Open: http://localhost:3000/workspace"
echo ""
echo "Logs: tail -f /tmp/langgraph.log /tmp/gateway.log /tmp/frontend.log"
