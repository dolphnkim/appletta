#!/bin/bash
# Appletta - Start Development Servers

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

# Start backend
echo -e "${YELLOW}[2/3] Starting backend server...${NC}"
cd backend || exit 1

# Check if virtual environment exists
if [ ! -d "venv" ] && [ ! -d "../venv" ]; then
    echo -e "${YELLOW}  No virtual environment found. Install dependencies first:${NC}"
    echo "  python -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Start backend in background
python main.py > ../backend.log 2>&1 &
BACKEND_PID=$!
echo -e "${GREEN}✓ Backend started (PID: $BACKEND_PID)${NC}"
echo "  http://localhost:8000"
echo "  API docs: http://localhost:8000/docs"
echo "  Logs: backend.log"

cd ..
echo ""

# Start frontend
echo -e "${YELLOW}[3/3] Starting frontend dev server...${NC}"
cd frontend || exit 1

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}  Installing frontend dependencies...${NC}"
    npm install
fi

# Start frontend in background
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}✓ Frontend started (PID: $FRONTEND_PID)${NC}"
echo "  http://localhost:5173"
echo "  Logs: frontend.log"

cd ..
echo ""

# Save PIDs for stop script
echo "$BACKEND_PID" > .backend.pid
echo "$FRONTEND_PID" > .frontend.pid

echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Appletta is running! 💜           ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "View logs:"
echo "  tail -f backend.log"
echo "  tail -f frontend.log"
echo ""
echo "Stop servers:"
echo "  ./stop.sh"
echo ""
