# Parser Deployment Guide

## Overview

This guide covers how to deploy new parsers or update existing ones without data loss or service interruption.

## Architecture Considerations

### Current Message Flow
```
Scraper → Redis/Celery → Notifier → Phone Parser → WebCrawler/Camoufox
```

### Services Using Parsers
- **Notifier Service** - Uses parsers during ad processing
- **Telegram Service** - May use parsers for user-requested extractions

## Deployment Strategy

### 1. Pre-Deployment Checklist

- [ ] Test new parser locally using `test_parser_extraction.py`
- [ ] Verify parser works with both WebCrawler and Camoufox (if applicable)
- [ ] Update `site_config.py` with new site configuration
- [ ] Ensure backward compatibility with existing parsers
- [ ] Create rollback plan

### 2. Code Changes Required

#### A. Add Site Configuration
```python
# common/utils/phone_utils/site_config.py
SITE_CONFIG = {
    # ... existing sites ...
    "newsite.com": {
        "service": ExtractionService.WEBCRAWLER,
        "methods": [RequestMethod.AIOHTTP, RequestMethod.CURL_CFFI],
        "description": "New Real Estate Site"
    }
}
```

#### B. Create Parser Module
```python
# common/utils/phone_utils/parsers/newsite_parser.py
from bs4 import BeautifulSoup
from common.utils.phone_utils.phone_models import ExtractionResult

def parse_newsite_page(html: str) -> ExtractionResult:
    """Parse phone numbers from newsite.com"""
    # Implementation
    pass
```

#### C. Update Phone Parser Router
```python
# common/utils/phone_utils/parsers/phone_parser.py
# Add to imports
from . import newsite_parser

# Add to routing logic
elif "newsite.com" in resource_url:
    result = newsite_parser.parse_newsite_page(html_content or "")
```

### 3. Deployment Options

## Option A: Blue-Green Deployment (Recommended)

This ensures zero downtime and easy rollback.

```yaml
# docker-compose.blue-green.yml
version: '3.8'

services:
  # Blue environment (current)
  notifier_service_blue:
    image: htode/notifier:current
    environment:
      - DEPLOYMENT=blue
    networks:
      - app_net

  # Green environment (new)
  notifier_service_green:
    image: htode/notifier:new
    environment:
      - DEPLOYMENT=green
    networks:
      - app_net

  # Load balancer to switch traffic
  notifier_lb:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - notifier_service_blue
      - notifier_service_green
```

### Deployment Steps:

1. **Build new image with parser changes**
```bash
docker build -t htode/notifier:new -f services/notifier_service/Dockerfile .
```

2. **Start green environment**
```bash
docker-compose -f docker-compose.blue-green.yml up -d notifier_service_green
```

3. **Verify green environment**
```bash
# Test the new parser
./test_parser_docker.sh "https://newsite.com/listing/123" --container notifier_service_green
```

4. **Drain blue queues**
```bash
# Stop accepting new tasks on blue
docker-compose exec notifier_service_blue celery control shutdown
```

5. **Switch traffic to green**
```bash
# Update load balancer or service discovery
docker-compose exec notifier_lb nginx -s reload
```

6. **Monitor and verify**
```bash
# Check logs
docker-compose logs -f notifier_service_green

# Monitor queue processing
docker-compose exec redis redis-cli LLEN celery
```

## Option B: Rolling Update with Queue Management

For simpler deployments with queue draining.

### Step 1: Prepare Deployment Script
```bash
#!/bin/bash
# deploy_parser.sh

set -e

echo "🚀 Starting parser deployment..."

# 1. Build new images
echo "📦 Building new images..."
docker-compose build notifier_service telegram_service

# 2. Stop workers from accepting new tasks
echo "⏸️  Pausing task consumption..."
docker-compose exec notifier_service celery control cancel_consumer
docker-compose exec telegram_service celery control cancel_consumer

# 3. Wait for current tasks to complete
echo "⏳ Waiting for tasks to complete..."
while [ $(docker-compose exec redis redis-cli LLEN celery | tr -d '\r') -gt 0 ]; do
    echo "Tasks remaining: $(docker-compose exec redis redis-cli LLEN celery | tr -d '\r')"
    sleep 5
done

# 4. Deploy new version
echo "🔄 Deploying new version..."
docker-compose up -d notifier_service telegram_service

# 5. Health check
echo "❤️  Health checking..."
sleep 10
./health_check.sh

echo "✅ Deployment complete!"
```

### Step 2: Health Check Script
```bash
#!/bin/bash
# health_check.sh

# Check service health
services=("notifier_service" "telegram_service" "webcrawler_service" "camoufox_service")

for service in "${services[@]}"; do
    if docker-compose ps $service | grep -q "Up"; then
        echo "✅ $service is healthy"
    else
        echo "❌ $service is not healthy"
        exit 1
    fi
done

# Test new parser
if [ -n "$NEW_SITE_URL" ]; then
    echo "🧪 Testing new parser..."
    ./test_parser_docker.sh "$NEW_SITE_URL"
fi
```

## Option C: Canary Deployment

Deploy to a small percentage of workers first.

```python
# common/utils/feature_flags.py
PARSER_ROLLOUT = {
    "newsite.com": {
        "enabled": True,
        "rollout_percentage": 10  # Start with 10% of traffic
    }
}

# In phone_parser.py
from common.utils.feature_flags import PARSER_ROLLOUT
import random

if "newsite.com" in resource_url:
    rollout = PARSER_ROLLOUT.get("newsite.com", {})
    if rollout.get("enabled") and random.randint(1, 100) <= rollout.get("rollout_percentage", 0):
        # Use new parser
        result = newsite_parser.parse_newsite_page(html_content)
    else:
        # Fall back to generic parser
        result = fallback_parser.fallback_parse(html_content)
```

## Message Queue Considerations

### 1. Celery/Redis (Current)

**Pros:**
- Simple task routing
- Built-in retry mechanisms
- Task result storage

**Cons:**
- No built-in message versioning
- Difficult to handle schema changes

**Best Practices:**
```python
# Version your tasks
@celery_app.task(name="notifier.process_ad.v2")
def process_ad_v2(ad_data: dict):
    # New implementation
    pass

# Keep old version during transition
@celery_app.task(name="notifier.process_ad.v1")
def process_ad_v1(ad_data: dict):
    # Forward to v2 with data transformation if needed
    return process_ad_v2(transform_ad_data(ad_data))
```

### 2. Alternative: RabbitMQ

**Benefits for deployments:**
- Message TTL
- Dead letter exchanges
- Better queue management

```yaml
# docker-compose with RabbitMQ
rabbitmq:
  image: rabbitmq:3-management
  environment:
    - RABBITMQ_DEFAULT_USER=user
    - RABBITMQ_DEFAULT_PASS=pass
  ports:
    - "5672:5672"
    - "15672:15672"  # Management UI
```

### 3. Alternative: Kafka

**Benefits for deployments:**
- Message replay capability
- Schema registry
- Better for event sourcing

```python
# With Kafka, you can replay messages after deployment
from kafka import KafkaConsumer

consumer = KafkaConsumer(
    'ads-topic',
    bootstrap_servers=['kafka:9092'],
    auto_offset_reset='earliest',  # Replay from beginning
    enable_auto_commit=False
)
```

## Deployment Automation

### GitHub Actions Workflow
```yaml
# .github/workflows/deploy-parser.yml
name: Deploy Parser Update

on:
  push:
    paths:
      - 'common/utils/phone_utils/parsers/**'
      - 'common/utils/phone_utils/site_config.py'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run parser tests
        run: |
          docker-compose up -d
          python test_parser_extraction.py --show-config
          # Add specific parser tests
      
  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy to production
        run: |
          # SSH to production and run deployment script
          ssh ${{ secrets.PROD_HOST }} 'cd /app && ./deploy_parser.sh'
```

## Rollback Procedures

### 1. Quick Rollback (Blue-Green)
```bash
# Switch back to blue
docker-compose exec notifier_lb nginx -s reload
```

### 2. Image Rollback
```bash
# Tag current as backup
docker tag htode/notifier:current htode/notifier:backup

# Rollback
docker-compose down notifier_service
docker tag htode/notifier:backup htode/notifier:current
docker-compose up -d notifier_service
```

### 3. Code Rollback
```bash
# Revert git changes
git revert HEAD
docker-compose build notifier_service
docker-compose up -d notifier_service
```

## Monitoring During Deployment

### 1. Queue Metrics
```python
# monitor_queues.py
import redis
import time

r = redis.Redis(host='localhost', port=6379)

while True:
    queues = {
        'celery': r.llen('celery'),
        'celery.dead': r.llen('celery.dead'),
        'celery.retry': r.llen('celery.retry')
    }
    print(f"Queue lengths: {queues}")
    time.sleep(5)
```

### 2. Error Tracking
```python
# Add to parser
import sentry_sdk

try:
    result = parse_site(html)
except Exception as e:
    sentry_sdk.capture_exception(e)
    # Fall back to generic parser
    result = fallback_parser.fallback_parse(html)
```

### 3. Performance Metrics
```python
# Add to extraction_client.py
import time
from prometheus_client import Histogram

extraction_time = Histogram(
    'parser_extraction_seconds',
    'Time spent extracting phone numbers',
    ['site', 'parser', 'service']
)

@extraction_time.labels(site='newsite.com', parser='newsite', service='webcrawler').time()
def extract_with_metrics():
    # Extraction logic
    pass
```

## Best Practices

1. **Always test in staging first**
2. **Use feature flags for gradual rollout**
3. **Monitor error rates during deployment**
4. **Keep old task versions for at least 24 hours**
5. **Document parser-specific behaviors**
6. **Version your message schemas**
7. **Have automated rollback triggers**

## Deployment Checklist

- [ ] Parser tested locally
- [ ] Parser tested in Docker
- [ ] Site configuration updated
- [ ] Phone parser routing updated
- [ ] Backward compatibility verified
- [ ] Deployment script prepared
- [ ] Monitoring dashboards ready
- [ ] Rollback plan documented
- [ ] Team notified of deployment window
- [ ] Queue draining strategy chosen 