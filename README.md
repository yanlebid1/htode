# htode - Multi-Bot Real Estate Notification System
### **A scalable, distributed microservices application for scraping real estate listings and delivering personalized notifications to 100,000+ users via Telegram using a multi-bot dispatcher architecture.**

## 🌟 Key Features

* **⚡ Ultra-Fast Notifications**: Multi-bot architecture delivers notifications to 100,000 users in just 3.3 minutes (vs 67 minutes with single bot)
* **🤖 Flower Bot Garden**: 20 beautifully themed Telegram bots (Orchid, Tulip, Daisy, etc.) for personalized user experience
* **🎯 Smart Filtering**: Advanced search criteria (location, price, rooms, floor preferences, pet-friendly options)
* **📱 Rich Media Support**: Property images, interactive galleries, and one-click contact
* **💾 Favorites Management**: Save and organize interesting properties
* **💳 Subscription System**: Free trial with integrated payment processing
* **🔐 Multi-Level Verification**: Email and phone verification systems
* **📊 Real-Time Monitoring**: Comprehensive system health monitoring and scaling tools

## 🏗️ Architecture Overview

This project implements a sophisticated **multi-bot dispatcher pattern** that overcomes Telegram's rate limits through horizontal scaling:

```
Users → Dispatcher Bot → Assignment → Pool Bot (1-20) → Notifications
                      ↓
               Bot Assignment Service
                      ↓
              Notification Distribution
```

### 🔧 Core Services

| Service | Purpose | Container Count |
|---------|---------|-----------------|
| **Dispatcher Service** | Main user entry point, assigns users to pool bots | 1 |
| **Pool Bot Service** | User interaction bots (Orchid, Tulip, etc.) | 1-20 |
| **Scraper Service** | Crawls real estate websites for new listings | 1+ |
| **Notifier Service** | Matches listings with user preferences | 1+ |
| **Telegram Service** | Advanced Telegram bot functionality | 1 |
| **Webcrawler Service** | Specialized web crawling with proxy support | 1+ |
| **Camoufox Service** | Browser automation service | 1+ |
| **WebApp Service** | Mini web applications for Telegram integration | 1 |

### 🚀 Performance Metrics

| Metric | Single Bot | Multi-Bot (20) | Improvement |
|--------|------------|----------------|-------------|
| **Users Supported** | 5,000 | 100,000 | 20x |
| **Notifications/Min** | 1,500 | 30,000 | 20x |
| **100k User Notification Time** | 67 minutes | 3.3 minutes | 20x faster |
| **Rate Limit Resilience** | ❌ | ✅ | Distributed load |

## 📁 Project Structure

```
htode/
├── services/                    # Microservices
│   ├── dispatcher_service/      # Main bot dispatcher
│   ├── pool_bot_service/        # Pool bot instances
│   ├── telegram_service/        # Advanced Telegram features
│   ├── scraper_service/         # Real estate scraping
│   ├── notifier_service/        # Notification processing
│   ├── webcrawler_service/      # Web crawling
│   ├── camoufox_service/        # Browser automation
│   └── webapps/                 # Mini web applications
├── common/                      # Shared modules
│   ├── db/                      # Database models & operations
│   ├── messaging/               # Inter-service communication
│   ├── services/                # Business logic services
│   ├── utils/                   # Utilities & helpers
│   ├── flows/                   # User interaction flows
│   └── verification/            # Verification systems
├── docs/                        # Documentation
├── scripts/                     # Deployment & monitoring tools
└── docker-compose.*.yml         # Container orchestration
```

## 🚀 Quick Start

### Prerequisites

* Docker and Docker Compose
* PostgreSQL database
* Redis (2 instances: queue + state)
* AWS S3 bucket (for image storage)
* 20+ Telegram bot tokens (from [@BotFather](https://t.me/BotFather))

### 1. Environment Setup

```bash
# Copy the multi-bot environment template
cp docs/env_multibot_template.txt .env

# Edit .env with your configuration:
# - Database credentials
# - Redis URLs
# - AWS S3 configuration  
# - Telegram bot tokens (dispatcher + 20 pool bots)
# - Payment processor credentials
```

### 2. Database Migration

```bash
# Initialize database with multi-bot schema
python scripts/migrate_multibot.py
```

### 3. Start with 2 Flower Bots (Testing)

```bash
# Start core infrastructure
docker-compose up -d postgres redis_queue redis_state

# Start dispatcher and first 2 flower bots
docker-compose -f docker-compose.multibot.yml up -d \
  dispatcher_bot \
  pool_bot_orchid pool_bot_tulip \
  pool_bot_worker_orchid pool_bot_worker_tulip
```

### 4. Monitor Your Flower Garden

```bash
# Real-time monitoring
python scripts/monitor_multibot_system.py

# Expected output:
# Multi-Bot System Monitor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Total Capacity: 10,000 users
# Current Users: 0 users
# Overall Utilization: 0.0%
#
# Bot Pool Status:
#  Bot Name    Username              Users  Capacity  Utilization  Status
#  orchid      @hto_de_orchid_bot   0      5,000     0.0%        AVAILABLE
#  tulip       @hto_de_tulip_bot    0      5,000     0.0%        AVAILABLE
```

### 5. Scale to Full Deployment (Optional)

```bash
# Generate full 20-bot configuration
python scripts/generate_full_multibot_compose.py --bots 20

# Deploy all 20 flower bots
docker-compose -f docker-compose.multibot-full.yml up -d
```

## 🌸 The Flower Bot Garden

Your users interact with beautifully themed flower bots:

| Flower | Bot | Meaning | Specialization |
|--------|-----|---------|----------------|
| 🌺 Orchid | [@hto_de_orchid_bot](https://t.me/hto_de_orchid_bot) | Elegance | Premium properties |
| 🌷 Tulip | [@hto_de_tulip_bot](https://t.me/hto_de_tulip_bot) | Perfect Love | Family homes |
| 🌼 Daisy | [@hto_de_daisy_bot](https://t.me/hto_de_daisy_bot) | Innocence | First-time buyers |
| 💜 Lavender | [@hto_de_lavender_bot](https://t.me/hto_de_lavender_bot) | Serenity | Peaceful areas |
| ... | ... | ... | ... |
| *+16 more beautiful flowers* |

## 🎯 User Journey

1. **Discovery**: User contacts any bot or the dispatcher
2. **Assignment**: System assigns user to their personal flower bot
3. **Personalization**: "Ваш персональний помічник - квітка Орхідея 🌺"
4. **Preferences Setup**: Configure search criteria via interactive menus
5. **Notifications**: Receive instant alerts for matching properties
6. **Interaction**: View galleries, contact agents, save favorites
7. **Subscription**: Manage trial period and premium features

## 💻 Development

### Adding New Services

1. Create service directory under `services/`
2. Implement using shared utilities from `common/`
3. Add Dockerfile and requirements.txt
4. Update docker-compose configuration
5. Add monitoring and health checks

### Extending Functionality

```python
# Example: Adding new real estate source
from common.utils.extraction_client import ExtractionClient
from common.db.operations import save_ads_batch

class NewSiteParser:
    def parse_listings(self, search_params):
        # Implement parsing logic
        listings = self.extract_data(search_params)
        return self.process_listings(listings)
```

### Testing

```bash
# Run comprehensive tests
./run_tests.sh

# Test specific components
python -m pytest tests/test_multibot_setup.py
python -m pytest tests/test_telegram_service.py
```

## 📊 Monitoring & Operations

### System Health

```bash
# Monitor all services
python scripts/monitor_multibot_system.py

# Check individual service health
docker-compose logs -f dispatcher_bot
docker-compose logs -f pool_bot_orchid

# Database operations
docker-compose exec postgres psql -U myuser -d mydb
```

### Scaling Operations

```bash
# Test notification throughput
python scripts/test_ultra_fast_notifications.py --users 10000

# Monitor browser pool scaling
python scripts/monitor_browser_pool.py

# Check Redis cluster performance  
python scripts/monitor_redis_cluster.py
```

## 🔧 Configuration

### Environment Variables

Key configuration areas:

```env
# Multi-Bot Configuration
TELEGRAM_DISPATCHER_TOKEN=your_dispatcher_token
BOT_POOL_1_TOKEN=orchid_bot_token
BOT_POOL_2_TOKEN=tulip_bot_token
# ... up to BOT_POOL_20_TOKEN

# Database & Cache
DB_HOST=postgres
REDIS_URL=redis://redis_queue:6379/0
REDIS_STATE_URL=redis://redis_state:6379/0

# External Services
AWS_S3_BUCKET=your_bucket
WAYFORPAY_MERCHANT_ACCOUNT=your_merchant_id
```

### Bot Pool Management

```python
# Automatic load balancing
from common.services.bot_assignment_service import BotAssignmentService

service = BotAssignmentService()
assigned_bot = service.assign_user_to_bot(user_id)
```

## 📖 Documentation

Comprehensive guides available in `docs/`:

* **[Multi-Bot Architecture](docs/MULTI_BOT_ARCHITECTURE.md)** - System design deep dive
* **[Deployment Guide](docs/MULTI_BOT_DEPLOYMENT_GUIDE.md)** - Production deployment
* **[Flower Bots Quick Start](docs/FLOWER_BOTS_QUICK_START.md)** - Bot garden setup
* **[Scaling Guide](docs/HORIZONTAL_SCALING.md)** - Performance optimization
* **[Browser Pool](docs/BROWSER_POOL_SCALING.md)** - Web scraping scaling
* **[Redis Clustering](docs/REDIS_CLUSTERING_SCALING.md)** - Cache optimization

## 🛠️ Troubleshooting

### Common Issues

**"All bots at capacity"**
```bash
# Increase bot capacity or add more bots
BOT_POOL_1_MAX_USERS=7500  # Increase from 5000
```

**Slow notifications**
```bash
# Check worker concurrency
docker-compose logs pool_bot_worker_orchid

# Monitor queue sizes
redis-cli llen telegram_bot_orchid_queue
```

**Bot not responding**
```bash
# Test bot token
curl https://api.telegram.org/bot<TOKEN>/getMe

# Check container logs
docker logs pool_bot_orchid --tail 100
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Follow the coding standards (type hints, docstrings, error handling)
4. Add tests for new functionality
5. Update documentation
6. Commit changes (`git commit -m 'Add amazing feature'`)
7. Push to branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## 📄 License

This project is private and proprietary. All rights reserved.

---

**Ready to deploy your flower bot garden? 🌸 Start with the [Quick Start](#-quick-start) guide!**

