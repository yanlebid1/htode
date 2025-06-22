# Scaling Notification System Guide

## Current Problem

When an ad is found:
1. Scraper inserts ad into DB (with phone extraction - SLOW)
2. Notifier sends to potentially thousands of users
3. Each notification task runs in the same queue

**Issues:**
- Phone extraction blocks ad insertion
- Thousands of notification tasks flood the queue
- No prioritization between ad processing and notifications

## Solution Architecture

### 1. Separate Phone Extraction from Ad Insertion

```python
# Current (BLOCKING)
def process_and_insert_ad():
    # Insert ad
    ad_id = create_ad()
    # Extract phones (SLOW - blocks everything)
    phones = extract_phone_numbers_from_resource(url)  
    # Store phones
    save_phones(phones)
```

```python
# New (ASYNC)
def process_and_insert_ad():
    # Insert ad quickly
    ad_id = create_ad()
    # Schedule async phone extraction
    celery_app.send_task(
        'extract_phones_for_ad',
        args=[ad_id, url],
        queue='phone_extraction_queue'
    )
```

### 2. Multiple Queue Strategy

```yaml
# docker-compose.yml
services:
  # High priority - ad processing
  notifier_worker_priority:
    command: celery -A app.celery_app worker -Q priority_queue -c 4
    
  # Medium priority - phone extraction  
  phone_extraction_worker:
    command: celery -A app.celery_app worker -Q phone_extraction_queue -c 8
    
  # Low priority - user notifications
  notification_worker:
    command: celery -A app.celery_app worker -Q notification_queue -c 16
```

### 3. Batch Notification Processing

Instead of thousands of individual tasks:

```python
# OLD: One task per user
for user_id in thousand_users:
    send_task('notify_user', args=[user_id, ad_id])

# NEW: Batch processing
user_batches = chunk_users(thousand_users, batch_size=100)
for batch in user_batches:
    send_task('notify_user_batch', args=[batch, ad_id])
```

## Implementation Changes

### Step 1: Update Ad Service

```python
# common/services/ad_service.py
@staticmethod
def process_and_insert_ad(db: Session, ad_data: Dict[str, Any], 
                         property_type: str, geo_id: int,
                         extract_phones: bool = False) -> Optional[int]:
    """
    Process and insert an ad. Phone extraction is now optional and async.
    """
    # ... existing ad creation code ...
    
    if extract_phones:
        # Schedule async extraction instead of blocking
        from common.celery_app import celery_app
        celery_app.send_task(
            'common.tasks.extract_phones_for_ad',
            args=[ad_id, resource_url],
            queue='phone_extraction_queue',
            priority=5  # Medium priority
        )
        logger.info("Scheduled phone extraction", extra={'ad_id': ad_id})
    
    return ad_id
```

### Step 2: Create Phone Extraction Task

```python
# common/tasks.py
from common.utils.task_versioning import versioned_task

@versioned_task('extract_phones_for_ad', version='v1')
def extract_phones_for_ad_v1(ad_id: int, resource_url: str):
    """Extract phones asynchronously after ad is created."""
    from common.utils.extraction_client import extraction_client
    from common.db.session import db_session
    from common.db.repositories.ad_repository import AdRepository
    
    try:
        # Use the new extraction client
        result = extraction_client.extract_content(
            url=resource_url,
            wait_after_load=3000
        )
        
        if result['status'] == 'success':
            # Parse phones from content
            from common.utils.phone_utils.parsers.phone_parser import (
                _extract_phone_numbers_async
            )
            phone_result = await _extract_phone_numbers_async(
                resource_url, 
                content=result.get('content')
            )
            
            # Store in database
            with db_session() as db:
                for phone in phone_result.phone_numbers:
                    AdRepository.add_phone(db, ad_id, phone)
                
                if phone_result.viber_link:
                    AdRepository.add_phone(db, ad_id, None, phone_result.viber_link)
                
                db.commit()
                
            logger.info(f"Extracted {len(phone_result.phone_numbers)} phones for ad {ad_id}")
            
            # Optionally trigger enriched notifications
            if phone_result.phone_numbers:
                celery_app.send_task(
                    'notify_users_with_phones',
                    args=[ad_id],
                    queue='notification_queue'
                )
    except Exception as e:
        logger.error(f"Phone extraction failed for ad {ad_id}: {e}")
        # Could retry or mark ad for manual review
```

### Step 3: Batch Notification System

```python
# common/messaging/batch_tasks.py
from typing import List
from common.utils.task_versioning import versioned_task

@versioned_task('notify_user_batch', version='v1')
def notify_user_batch_v1(user_ids: List[int], ad_data: dict):
    """Send notifications to a batch of users."""
    from common.messaging.service import messaging_service
    import asyncio
    
    async def send_batch():
        tasks = []
        for user_id in user_ids:
            task = messaging_service.send_ad(
                user_id=user_id,
                ad_data=ad_data,
                # Don't wait for phones - they'll be added later
                include_phones=False
            )
            tasks.append(task)
        
        # Send all notifications concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r and not isinstance(r, Exception))
        logger.info(f"Batch sent: {success_count}/{len(user_ids)} successful")
        
        return success_count
    
    return asyncio.run(send_batch())
```

### Step 4: Update Notifier Service

```python
# services/notifier_service/app/tasks.py
@celery_app.task(name="notifier_service.app.tasks.sort_and_notify_new_ads")
def sort_and_notify_new_ads(new_ads):
    """Enhanced version with batching."""
    BATCH_SIZE = 100
    
    for ad in new_ads:
        ad_id = ad.get('id')
        users_to_notify = find_users_for_ad(ad)
        
        if len(users_to_notify) > BATCH_SIZE:
            # Batch large user sets
            for i in range(0, len(users_to_notify), BATCH_SIZE):
                batch = users_to_notify[i:i + BATCH_SIZE]
                celery_app.send_task(
                    'notify_user_batch',
                    args=[batch, ad],
                    queue='notification_queue',
                    priority=1  # Low priority
                )
        else:
            # Small sets can go individually
            for user_id in users_to_notify:
                _notify_user_about_ad(user_id, ad, s3_image_urls)
```

## Queue Configuration

### Redis Priority Queues

```python
# common/celery_app.py
from kombu import Queue, Exchange

celery_app.conf.task_routes = {
    'scraper_service.*': {'queue': 'scraper_queue'},
    'extract_phones_for_ad': {'queue': 'phone_extraction_queue'},
    'notify_user_batch': {'queue': 'notification_queue'},
    'send_ad_with_extra_buttons': {'queue': 'telegram_queue'},
}

celery_app.conf.task_queue_max_priority = 10
celery_app.conf.task_default_priority = 5

celery_app.conf.task_queues = (
    Queue('scraper_queue', priority=10),          # Highest
    Queue('phone_extraction_queue', priority=5),  # Medium
    Queue('notification_queue', priority=1),      # Lowest
    Queue('telegram_queue', priority=3),          # Low-Medium
)
```

## Monitoring Improvements

```python
# monitor_deployment.py updates
def get_queue_details(self) -> Dict[str, Dict]:
    """Get detailed queue information."""
    queues = {
        'scraper_queue': {
            'length': self.redis_client.llen('scraper_queue'),
            'purpose': 'Ad fetching',
            'workers': 2
        },
        'phone_extraction_queue': {
            'length': self.redis_client.llen('phone_extraction_queue'),
            'purpose': 'Phone extraction',
            'workers': 8
        },
        'notification_queue': {
            'length': self.redis_client.llen('notification_queue'),
            'purpose': 'User notifications',
            'workers': 16
        },
        'telegram_queue': {
            'length': self.redis_client.llen('telegram_queue'),
            'purpose': 'Telegram messages',
            'workers': 8
        }
    }
    
    # Calculate processing rate per queue
    for queue_name, info in queues.items():
        rate_key = f"{queue_name}_processed"
        processed = self.redis_client.get(rate_key) or 0
        info['rate'] = int(processed) / 60  # per minute
    
    return queues
```

## Scaling Strategy

### For 10,000 Users per Ad:

1. **Batch Size**: 100 users = 100 batch tasks instead of 10,000 individual tasks
2. **Worker Distribution**:
   - 2 workers for scraping (low volume)
   - 8 workers for phone extraction (CPU intensive)
   - 16 workers for notifications (I/O bound)
   - 8 workers for Telegram API (rate limited)

3. **Processing Time**:
   - Ad insertion: <1 second
   - Phone extraction: 2-5 seconds (async, doesn't block)
   - Batch notification: ~10 seconds per 100 users
   - Total time for 10k users: ~17 minutes (vs hours before)

### Redis Memory Optimization

```python
# Expire completed tasks quickly
celery_app.conf.result_expires = 3600  # 1 hour

# Don't store results for notification tasks
@celery_app.task(ignore_result=True)
def send_notification_task():
    pass
```

## Migration Plan

1. **Phase 1**: Deploy new tasks alongside old ones
2. **Phase 2**: Route 10% traffic to new system
3. **Phase 3**: Monitor and increase to 50%
4. **Phase 4**: Full migration

This architecture handles your scale requirements efficiently! 