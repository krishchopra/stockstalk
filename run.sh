#!/bin/bash

# StockStalk startup script

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}StockStalk - Stock Monitoring App${NC}"
echo "=================================="
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv .venv
    source .venv/bin/activate
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install uv
    uv pip install -e .
else
    source .venv/bin/activate
fi

# Check for config file
if [ ! -f "config.json" ]; then
    echo -e "${YELLOW}Config file not found. Creating default...${NC}"
    python -m stockstalk --once
    echo ""
    echo -e "${YELLOW}Default config created. Edit config.json to customize.${NC}"
    echo ""
fi

# Run based on argument
case "${1:-run}" in
    configure)
        echo "Starting configuration UI..."
        python -m stockstalk --configure
        ;;
    server)
        PORT="${2:-5000}"
        echo "Starting API server on port $PORT..."
        python -m stockstalk --server --port "$PORT"
        ;;
    once)
        echo "Running analysis once..."
        python -m stockstalk --once
        ;;
    test)
        echo "Running tests..."
        pytest
        ;;
    format)
        echo "Formatting code..."
        black stockstalk/ tests/
        ;;
    run|*)
        echo "Starting continuous monitoring..."
        echo "Press Ctrl+C to stop"
        echo ""
        python -m stockstalk
        ;;
esac
