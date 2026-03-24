#!/bin/bash
# Build CongressFish agents

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found. Copy .env.example and add your API keys."
    exit 1
fi

# Parse arguments
MODE="${1:-full}"

case "$MODE" in
    full)
        echo "Building full Congress graph..."
        python backend/agents/build.py --full
        ;;
    senate)
        echo "Building Senate only (test mode)..."
        python backend/agents/build.py --senate-only
        ;;
    house)
        echo "Building House only..."
        python backend/agents/build.py --house-only
        ;;
    data)
        echo "Downloading data only (no persona generation)..."
        python backend/agents/build.py --data-only --full
        ;;
    personas)
        echo "Generating personas for existing profiles..."
        python backend/agents/build.py --personas-only
        ;;
    *)
        echo "Usage: $0 [full|senate|house|data|personas]"
        echo ""
        echo "full    - Full Congress + SCOTUS + Executive + Orgs (slow, ~1 hour)"
        echo "senate  - Senate members only (fast test, ~5 min)"
        echo "house   - House members only (slow, ~30 min)"
        echo "data    - Download data only, no persona generation"
        echo "personas - Generate personas for existing profiles"
        exit 1
        ;;
esac
