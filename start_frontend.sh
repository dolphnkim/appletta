#!/bin/bash
# Appletta - Start Frontend Only

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Starting Appletta Frontend       ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

# Check if node_modules exists
echo -e "${YELLOW}[1/2] Checking dependencies...${NC}"
cd frontend
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}  Installing frontend dependencies...${NC}"
    npm install
fi
echo -e "${GREEN}✓ Frontend dependencies ready${NC}"

echo ""
echo -e "${YELLOW}[2/2] Starting frontend server...${NC}"
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Frontend Starting! 💜             ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo "Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop the frontend"
echo ""

npm run dev
