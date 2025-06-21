#!/bin/bash
# Run parser extraction test inside Docker network

# Check if URL is provided
if [ -z "$1" ]; then
    echo "Usage: ./test_parser_docker.sh <URL> [options]"
    echo ""
    echo "Examples:"
    echo "  ./test_parser_docker.sh https://www.olx.ua/d/uk/obyavlenie/..."
    echo "  ./test_parser_docker.sh https://lun.ua/... --service webcrawler --method curl_cffi"
    echo "  ./test_parser_docker.sh https://dom.ria.com/... --service camoufox"
    echo "  ./test_parser_docker.sh --show-config"
    exit 1
fi

# Run the test using docker-compose exec
echo "🐳 Running parser test in Docker..."
docker-compose exec -e DOCKER_ENV=1 telegram_service python /app/test_parser_extraction.py "$@" 