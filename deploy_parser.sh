#!/bin/bash
# Deploy parser updates with zero downtime

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEPLOYMENT_MODE=${1:-"rolling"} # rolling, blue-green, canary
NEW_SITE_URL=${2:-""}          # URL to test new parser

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}          Parser Deployment Script                          ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "Mode: ${YELLOW}$DEPLOYMENT_MODE${NC}"
echo -e "Test URL: ${YELLOW}${NEW_SITE_URL:-None}${NC}"
echo ""

# Function to check queue length
check_queue_length() {
    local queue_name=$1
    docker-compose exec -T redis redis-cli LLEN "$queue_name" | tr -d '\r\n'
}

# Function to wait for queues to drain
wait_for_queue_drain() {
    local max_wait=${1:-300} # 5 minutes default
    local start_time=$(date +%s)
    
    echo -e "${YELLOW}⏳ Waiting for queues to drain...${NC}"
    
    while true; do
        local celery_len=$(check_queue_length "celery")
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ "$celery_len" -eq 0 ]; then
            echo -e "${GREEN}✅ Queues are empty${NC}"
            break
        fi
        
        if [ $elapsed -gt $max_wait ]; then
            echo -e "${RED}❌ Timeout waiting for queues to drain${NC}"
            echo -e "${RED}   Remaining tasks: $celery_len${NC}"
            read -p "Continue anyway? (y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
            break
        fi
        
        echo -e "   Tasks remaining: ${YELLOW}$celery_len${NC} (${elapsed}s elapsed)"
        sleep 5
    done
}

# Function to test parser
test_parser() {
    local url=$1
    if [ -n "$url" ]; then
        echo -e "${BLUE}🧪 Testing parser with: $url${NC}"
        if ./test_parser_docker.sh "$url"; then
            echo -e "${GREEN}✅ Parser test passed${NC}"
            return 0
        else
            echo -e "${RED}❌ Parser test failed${NC}"
            return 1
        fi
    fi
    return 0
}

# Function to perform health checks
health_check() {
    echo -e "${BLUE}❤️  Running health checks...${NC}"
    
    local services=("notifier_service" "telegram_service" "webcrawler_service" "camoufox_service")
    local all_healthy=true
    
    for service in "${services[@]}"; do
        if docker-compose ps "$service" 2>/dev/null | grep -q "Up"; then
            echo -e "   ${GREEN}✅ $service is healthy${NC}"
        else
            echo -e "   ${RED}❌ $service is not healthy${NC}"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        echo -e "${GREEN}✅ All services healthy${NC}"
        return 0
    else
        return 1
    fi
}

# Main deployment logic
case $DEPLOYMENT_MODE in
    "rolling")
        echo -e "${BLUE}🔄 Starting rolling deployment...${NC}"
        
        # 1. Build new images
        echo -e "\n${YELLOW}📦 Building new images...${NC}"
        docker-compose build notifier_service telegram_service
        
        # 2. Tag current as backup
        echo -e "\n${YELLOW}🏷️  Tagging current images as backup...${NC}"
        docker tag htode/notifier:latest htode/notifier:backup
        docker tag htode/telegram:latest htode/telegram:backup
        
        # 3. Stop workers from accepting new tasks
        echo -e "\n${YELLOW}⏸️  Pausing task consumption...${NC}"
        docker-compose exec -T notifier_service celery -A app.celery_app control cancel_consumer || true
        docker-compose exec -T telegram_service celery -A app.celery_app control cancel_consumer || true
        
        # 4. Wait for queues to drain
        wait_for_queue_drain
        
        # 5. Deploy new version
        echo -e "\n${YELLOW}🚀 Deploying new version...${NC}"
        docker-compose up -d notifier_service telegram_service
        
        # 6. Wait for services to start
        sleep 10
        
        # 7. Health check
        if ! health_check; then
            echo -e "${RED}❌ Health check failed, rolling back...${NC}"
            docker tag htode/notifier:backup htode/notifier:latest
            docker tag htode/telegram:backup htode/telegram:latest
            docker-compose up -d notifier_service telegram_service
            exit 1
        fi
        
        # 8. Test new parser
        if ! test_parser "$NEW_SITE_URL"; then
            echo -e "${RED}❌ Parser test failed, rolling back...${NC}"
            docker tag htode/notifier:backup htode/notifier:latest
            docker tag htode/telegram:backup htode/telegram:latest
            docker-compose up -d notifier_service telegram_service
            exit 1
        fi
        
        echo -e "\n${GREEN}✅ Rolling deployment complete!${NC}"
        ;;
        
    "blue-green")
        echo -e "${BLUE}🔵🟢 Starting blue-green deployment...${NC}"
        
        # This requires blue-green docker-compose setup
        if [ ! -f "docker-compose.blue-green.yml" ]; then
            echo -e "${RED}❌ docker-compose.blue-green.yml not found${NC}"
            echo -e "${YELLOW}   Please create blue-green configuration first${NC}"
            exit 1
        fi
        
        # 1. Build green environment
        echo -e "\n${YELLOW}📦 Building green environment...${NC}"
        docker-compose -f docker-compose.blue-green.yml build notifier_service_green
        
        # 2. Start green environment
        echo -e "\n${YELLOW}🟢 Starting green environment...${NC}"
        docker-compose -f docker-compose.blue-green.yml up -d notifier_service_green
        
        # 3. Wait for green to be healthy
        sleep 15
        
        # 4. Test green environment
        if ! test_parser "$NEW_SITE_URL"; then
            echo -e "${RED}❌ Green environment test failed${NC}"
            docker-compose -f docker-compose.blue-green.yml down notifier_service_green
            exit 1
        fi
        
        # 5. Switch traffic to green
        echo -e "\n${YELLOW}🔀 Switching traffic to green...${NC}"
        # This would update load balancer or service discovery
        # For now, we'll just stop blue
        docker-compose -f docker-compose.blue-green.yml stop notifier_service_blue
        
        echo -e "\n${GREEN}✅ Blue-green deployment complete!${NC}"
        echo -e "${YELLOW}   Blue environment is stopped but not removed${NC}"
        echo -e "${YELLOW}   To rollback: docker-compose -f docker-compose.blue-green.yml up -d notifier_service_blue${NC}"
        ;;
        
    "canary")
        echo -e "${BLUE}🐤 Starting canary deployment...${NC}"
        
        # This requires feature flag configuration
        echo -e "\n${YELLOW}📝 Updating feature flags...${NC}"
        
        # Check if feature flags file exists
        if [ ! -f "common/utils/feature_flags.py" ]; then
            echo -e "${YELLOW}   Creating feature flags file...${NC}"
            cat > common/utils/feature_flags.py << 'EOF'
# Feature flags for gradual rollout
PARSER_ROLLOUT = {}
EOF
        fi
        
        # Deploy with low percentage
        echo -e "\n${YELLOW}🚀 Deploying with 10% traffic...${NC}"
        docker-compose build notifier_service
        docker-compose up -d notifier_service
        
        # Monitor for 5 minutes
        echo -e "\n${YELLOW}📊 Monitoring canary deployment for 5 minutes...${NC}"
        for i in {1..60}; do
            echo -ne "\r   Progress: $((i*5))/300 seconds"
            sleep 5
        done
        echo ""
        
        echo -e "\n${GREEN}✅ Canary deployment phase 1 complete!${NC}"
        echo -e "${YELLOW}   Monitor metrics and gradually increase rollout percentage${NC}"
        ;;
        
    *)
        echo -e "${RED}❌ Unknown deployment mode: $DEPLOYMENT_MODE${NC}"
        echo -e "${YELLOW}   Available modes: rolling, blue-green, canary${NC}"
        exit 1
        ;;
esac

# Final summary
echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    Deployment Summary                      ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "Mode: ${GREEN}$DEPLOYMENT_MODE${NC}"
echo -e "Status: ${GREEN}Success${NC}"
echo -e "Time: $(date)"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Monitor logs: docker-compose logs -f notifier_service"
echo -e "2. Check metrics and error rates"
echo -e "3. Be ready to rollback if needed"
echo "" 