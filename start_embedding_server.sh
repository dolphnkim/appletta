#!/bin/bash
# Appletta - Start Qwen3-Embedding Server

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Starting Qwen3-Embedding Server    ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

# Configuration
MODEL_PATH="/Users/kimwhite/models/Qwen/Embedding-8B-mlx-8bit"
PORT=${PORT:-8100}

# Check if model exists
echo -e "${YELLOW}[1/2] Checking model...${NC}"
if [ ! -d "$MODEL_PATH" ]; then
    echo -e "${RED}✗ Model not found at: $MODEL_PATH${NC}"
    echo "  Please run the conversion script first:"
    echo "  python scripts/convert_qwen_embedding_8bit.py"
    exit 1
fi
echo -e "${GREEN}✓ Model found: Qwen3-Embedding-8B (8-bit MLX)${NC}"

echo ""
echo -e "${YELLOW}[2/2] Starting embedding server on port $PORT...${NC}"
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Embedding Server Starting! 🧠     ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo "Embedding Server: http://localhost:$PORT"
echo "Health Check:     http://localhost:$PORT/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Find the right Python
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v /opt/homebrew/bin/python3.11 &> /dev/null; then
    PYTHON="/opt/homebrew/bin/python3.11"
else
    PYTHON="python3"
fi

# Start the server
EMBEDDING_MODEL_PATH="$MODEL_PATH" PORT="$PORT" $PYTHON -m backend.services.qwen_embedding_server
