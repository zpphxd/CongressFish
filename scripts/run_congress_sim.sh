#!/bin/bash
# Run a CongressFish bill simulation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check if backend is running
if ! curl -s http://localhost:5000/api/health > /dev/null 2>&1; then
    echo "Error: Backend not running. Start it first:"
    echo "  cd backend && python run.py"
    exit 1
fi

BILL_TITLE="${1:-A bill to do something}"

echo "Starting CongressFish simulation..."
echo "Bill: $BILL_TITLE"
echo ""

# Call the simulation API
curl -X POST http://localhost:5000/api/congress/simulate \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"$BILL_TITLE\", \"summary\": \"Test bill\", \"chamber\": \"house\"}" \
    | jq .

echo ""
echo "Simulation started. Check the dashboard at http://localhost:3000/congress"
