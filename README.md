# htode
### **A distributed microservices application for scraping real estate listings and sending personalized notifications to users via Telegram based on their preferences.**

### System Overview
This project consists of several microservices working together to provide real-time real estate listing notifications:

* Scraper Service: Periodically fetches new real estate listings from external sources
* Notifier Service: Processes listings and determines which users to notify based on their preferences
* Telegram Service: Provides a Telegram bot interface for users to manage their preferences and receive notifications
* Web App Service: Provides mini web apps for Telegram integration (image galleries, phone number displays)

The services communicate through Redis (for messaging via Celery) and share a PostgreSQL database.


### Features

* Real-Time Monitoring: Continuously monitors real estate listings from popular sites
* Custom Filter Criteria: Users can set detailed search preferences (location, price range, room count, etc.)
* Instant Notifications: Get alerts as soon as matching properties become available
* Rich Media Support: View property images and details directly in Telegram
* One-Click Contact: Call property agents directly from the notification
* Favorites List: Save and organize interesting properties
* User Subscription Management: Free trial period with subscription tracking

## Setup and Installation
### Prerequisites

* Docker and Docker Compose
* AWS Account with S3 bucket configured (for image storage)
* Telegram Bot Token (obtain from BotFather)

### Environment Variables

Create a `.env` file in the project root with the following variables:


```
# Database Configuration
DB_HOST=postgres
DB_PORT=5432
DB_USER=myuser
DB_PASS=mypass
DB_NAME=mydb

# Redis Configuration
REDIS_URL=redis://redis:6379/0

# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=eu-west-1
AWS_S3_BUCKET=your_bucket_name
AWS_S3_BUCKET_PREFIX=ads-images/
CLOUDFRONT_DOMAIN=your_cloudfront_domain  # Optional

# Telegram Configuration
TELEGRAM_TOKEN=your_telegram_bot_token
Starting the Services
```
### Starting the Services

1. Build and start all services:
`docker-compose up -d`
2. Initialize the database (if not already done):
`docker-compose exec postgres psql -U myuser -d mydb -f /docker-entrypoint-initdb.d/init.sql`
3. Trigger initial data scraping:
`docker-compose exec scraper_worker_service celery -A scraper_service.app.celery_app call scraper_service.app.tasks.initial_30_day_scrape`

### Usage

#### Bot Commands

* `/start` - Begin interaction with the bot and set up your preferences
* `/menu` - Show the main menu
* `/cancel` - Cancel the current operation

#### Setting Up Preferences

1. Start the bot with /start 
2. Follow the prompts to select:
   * Property type (apartment, house)
   * City
   * Number of rooms
   * Price range
   * Additional criteria (floor preferences, pets allowed, etc.)

#### Managing Subscriptions
The main menu offers options to:

* View current subscriptions
* Enable/disable notifications
* Edit search preferences
* View saved favorites

### Architecture Details
#### Message Flow

1. The Scraper Service periodically checks for new listings
2. New listings are stored in the database
3. The Notifier Service matches listings with user preferences
4. Matching notifications are sent to users via the Telegram Service

#### Error Handling and Reliability

1. Task retries with exponential backoff
2. Comprehensive error logging
3. Message validation for inter-service communication


### Development Guide

#### Adding a New Service

1. Create a new directory under `services/`
2. Create a Dockerfile for the service
3. Add the service to `docker-compose.yml`
4. Implement the service using the shared utilities from `common/`

#### Extending Functionality
The system is designed to be modular, making it easy to add new features:

1. To add support for a new real estate source:
   * Create a new scraper in the Scraper Service
   * Update the matching logic in the Notifier Service if needed
2. To add new notification channels:
   * Create a new service or extend the existing Telegram Service
   * Add new Celery tasks for sending notifications


### Code Style
This project follows these coding practices:

1. Python code uses type hints where possible
2. Functions have docstrings explaining their purpose and parameters
3. Error handling with appropriate logging
4. Centralized configuration through environment variables


### Monitoring and Maintenance
#### Logs
All services log to stdout/stderr, which can be viewed using Docker: `docker-compose logs -f [service_name]`

#### Database Maintenance
To access the PostgreSQL database: `docker-compose exec postgres psql -U myuser -d mydb`

#### Redis Inspection
To inspect the Redis queues:
`docker-compose exec redis redis-cli`


### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request