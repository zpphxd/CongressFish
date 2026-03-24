#!/bin/bash
# Refresh CongressFish agent data

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

MODE="${1:-fast}"

case "$MODE" in
    fast)
        echo "Fast refresh (check votes/trades only)..."
        python backend/agents/refresh.py
        ;;
    full)
        echo "Full refresh (re-download all data)..."
        python backend/agents/refresh.py --full
        ;;
    trades)
        echo "Refresh stock trades only..."
        python backend/agents/refresh.py --trades
        ;;
    votes)
        echo "Refresh roll call votes only..."
        python backend/agents/refresh.py --votes
        ;;
    *)
        echo "Usage: $0 [fast|full|trades|votes]"
        echo ""
        echo "fast  - Check for vote/trade changes (~5 min)"
        echo "full  - Re-download all data (~30-45 min)"
        echo "trades - Stock trades only (~2 min)"
        echo "votes - Roll call votes only (~5 min)"
        exit 1
        ;;
esac
