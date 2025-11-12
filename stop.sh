#!/bin/bash
# Appletta - Stop Development Servers

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    Stopping Appletta Dev Servers      ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

# Check if tmux session exists
if tmux has-session -t appletta 2>/dev/null; then
    echo -e "${YELLOW}Stopping tmux session...${NC}"
    tmux kill-session -t appletta
    echo -e "${GREEN}✓ Tmux session stopped${NC}"
else
    echo -e "${YELLOW}No tmux session found${NC}"
fi

# Clean up any remaining processes (fallback)
if pkill -f "python.*backend.main" 2>/dev/null; then
    echo -e "${GREEN}✓ Backend processes stopped${NC}"
fi

if pkill -f "vite" 2>/dev/null; then
    echo -e "${GREEN}✓ Frontend processes stopped${NC}"
fi

# Clean up old PID files if they exist
rm -f .backend.pid .frontend.pid

echo ""
echo -e "${GREEN}All servers stopped${NC}"
