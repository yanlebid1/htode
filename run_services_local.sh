#!/bin/bash
# Run extraction services locally for testing

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting extraction services locally...${NC}"

# Function to check if port is available
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        echo -e "${RED}Port $port is already in use!${NC}"
        return 1
    fi
    return 0
}

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down services...${NC}"
    # Kill all background processes
    jobs -p | xargs -r kill
    exit 0
}

# Set trap for cleanup
trap cleanup INT TERM

# Check ports
echo "Checking ports..."
if ! check_port 8100; then
    echo "Please stop the service using port 8100"
    exit 1
fi

if ! check_port 8200; then
    echo "Please stop the service using port 8200"
    exit 1
fi

# Create temporary directories for logs
mkdir -p logs

# Start WebCrawler service
echo -e "\n${GREEN}Starting WebCrawler service on port 8200...${NC}"
cd services/webcrawler_service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8200 --reload > ../../logs/webcrawler.log 2>&1 &
WEBCRAWLER_PID=$!
cd ../..
echo "WebCrawler PID: $WEBCRAWLER_PID"

# Start Camoufox service
echo -e "\n${GREEN}Starting Camoufox service on port 8100...${NC}"
cd services/camoufox_service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload > ../../logs/camoufox.log 2>&1 &
CAMOUFOX_PID=$!
cd ../..
echo "Camoufox PID: $CAMOUFOX_PID"

# Wait a bit for services to start
echo -e "\n${YELLOW}Waiting for services to start...${NC}"
sleep 5

# Check if services are running
echo -e "\n${GREEN}Checking service health...${NC}"

# Check WebCrawler
if curl -s http://localhost:8200/health > /dev/null; then
    echo -e "✅ WebCrawler service is ${GREEN}healthy${NC}"
else
    echo -e "❌ WebCrawler service is ${RED}not responding${NC}"
fi

# Check Camoufox
if curl -s http://localhost:8100/health > /dev/null; then
    echo -e "✅ Camoufox service is ${GREEN}healthy${NC}"
else
    echo -e "❌ Camoufox service is ${RED}not responding${NC}"
fi

echo -e "\n${GREEN}Services are running!${NC}"
echo -e "${YELLOW}Logs are available in:${NC}"
echo "  - WebCrawler: logs/webcrawler.log"
echo "  - Camoufox: logs/camoufox.log"
echo ""
echo -e "${YELLOW}To test extraction, run:${NC}"
echo "  python test_parser_extraction.py <URL>"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"

# Keep script running
while true; do
    sleep 1
done 