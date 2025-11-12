#!/bin/bash
# Appletta - Start Development Servers with tmux

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Starting Appletta Dev Servers    ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

# Check if PostgreSQL is running
echo -e "${YELLOW}[1/3] Checking PostgreSQL...${NC}"
if ! pg_isready -q; then
    echo -e "${RED}✗ PostgreSQL is not running${NC}"
    echo "  Start PostgreSQL and try again"
    exit 1
fi
echo -e "${GREEN}✓ PostgreSQL is running${NC}"

# Check if database exists
if ! psql -lqt | cut -d \| -f 1 | grep -qw appletta; then
    echo -e "${YELLOW}  Creating database 'appletta'...${NC}"
    createdb appletta
    if [ -f "scripts/schema.sql" ]; then
        echo -e "${YELLOW}  Applying schema...${NC}"
        psql appletta < scripts/schema.sql
        echo -e "${GREEN}✓ Database initialized${NC}"
    fi
else
    echo -e "${GREEN}✓ Database 'appletta' exists${NC}"
fi

echo ""

# Check if virtual environment exists
echo -e "${YELLOW}[2/3] Checking dependencies...${NC}"
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗ No virtual environment found. Install dependencies first:${NC}"
    echo "  python -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi
echo -e "${GREEN}✓ Virtual environment found${NC}"

# Check if node_modules exists
cd frontend
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}  Installing frontend dependencies...${NC}"
    npm install
fi
cd ..
echo -e "${GREEN}✓ Frontend dependencies ready${NC}"

echo ""
echo -e "${YELLOW}[3/3] Starting servers in tmux...${NC}"
echo ""

# Kill any existing appletta tmux session
tmux has-session -t appletta 2>/dev/null && tmux kill-session -t appletta

# Get absolute path to project root
PROJECT_ROOT=$(pwd)

# Start a new tmux session with 3 panes
tmux new-session -d -s appletta -n "appletta"

# Split window horizontally for backend (top) and frontend (bottom)
tmux split-window -v -t appletta

# Select the top pane for backend
tmux select-pane -t 0
tmux send-keys "cd '$PROJECT_ROOT'" C-m
tmux send-keys "source .venv/bin/activate" C-m
tmux send-keys "echo '🔧 BACKEND (http://localhost:8000)'" C-m
tmux send-keys "echo 'API Docs: http://localhost:8000/docs'" C-m
tmux send-keys "echo ''" C-m
tmux send-keys "python -m backend.main" C-m

# Select the bottom pane for frontend
tmux select-pane -t 1
tmux send-keys "cd '$PROJECT_ROOT/frontend'" C-m
tmux send-keys "echo '⚛️  FRONTEND (http://localhost:5173)'" C-m
tmux send-keys "echo ''" C-m
tmux send-keys "npm run dev" C-m

# Attach to the session
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Appletta is starting! 💜          ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+B then D to detach from tmux"
echo "Run 'tmux attach -t appletta' to reattach"
echo "Run './stop.sh' to stop all servers"
echo ""
echo "Attaching to tmux session in 2 seconds..."
sleep 2

tmux attach-session -t appletta
