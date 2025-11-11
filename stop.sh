#!/bin/bash
# Appletta - Stop Development Servers

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    Stopping Appletta Dev Servers      ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

# Stop backend
if [ -f ".backend.pid" ]; then
    BACKEND_PID=$(cat .backend.pid)
    if ps -p $BACKEND_PID > /dev/null; then
        kill $BACKEND_PID
        echo -e "${GREEN}✓ Backend stopped${NC}"
    fi
    rm .backend.pid
fi

# Stop frontend
if [ -f ".frontend.pid" ]; then
    FRONTEND_PID=$(cat .frontend.pid)
    if ps -p $FRONTEND_PID > /dev/null; then
        kill $FRONTEND_PID
        echo -e "${GREEN}✓ Frontend stopped${NC}"
    fi
    rm .frontend.pid
fi

# Clean up any remaining processes
pkill -f "python.*backend.main"
pkill -f "vite"

echo ""
echo -e "${GREEN}All servers stopped${NC}"
