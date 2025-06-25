# Multi-Bot Dispatcher Architecture

## Overview

This document describes the implementation of a dispatcher bot pattern with a pool of subscription-mailing bots to handle mass notifications at scale, overcoming Telegram's rate limits.

## Problem Statement

- **Single Bot Limitation**: 30 messages/second (1,800/minute)
- **100k Users**: Would take ~67 minutes to notify all
- **Unacceptable Delay**: Real-time notifications become stale

## Solution: Dispatcher Pattern with Bot Pool

### Architecture Overview

```
Users → Dispatcher Bot → Assignment → Pool Bot (1-20) → Notifications
```

### Key Benefits

1. **Linear Scaling**: 
   - 1 bot = 1,500 users/min
   - 20 bots = 30,000 users/min
   - 100k users in **3.3 minutes** vs 67 minutes!

2. **Fault Tolerance**: Individual bot failures don't affect others
3. **Load Balancing**: Even distribution across bots
4. **Easy Scaling**: Add more bots as needed

## Implementation Components

### 1. Database Schema Updates

```sql
-- Add to users table
ALTER TABLE users ADD COLUMN assigned_bot_name VARCHAR(50);
ALTER TABLE users ADD COLUMN assigned_bot_username VARCHAR(100);
ALTER TABLE users ADD COLUMN assignment_date TIMESTAMP;
ALTER TABLE users ADD COLUMN dispatcher_chat_id VARCHAR(50);

CREATE INDEX idx_users_assigned_bot ON users(assigned_bot_name);
```

### 2. Configuration Structure

```python
# .env file
TELEGRAM_DISPATCHER_TOKEN=your_dispatcher_token
TELEGRAM_DISPATCHER_USERNAME=@YourMainBot

BOT_POOL_1_TOKEN=bot1_token
BOT_POOL_1_USERNAME=@YourBot_1
BOT_POOL_1_MAX_USERS=5000

BOT_POOL_2_TOKEN=bot2_token
BOT_POOL_2_USERNAME=@YourBot_2
BOT_POOL_2_MAX_USERS=5000

# ... up to 20 bots for 100k users
```

### 3. User Flow

1. **New User Journey**:
   ```
   User starts → Dispatcher Bot → Check pool capacity → 
   Assign to bot with most space → Redirect to assigned bot
   ```

2. **Notification Flow**:
   ```
   New Ad → Group users by assigned bot → 
   Send batches to each bot's queue → Parallel processing
   ```

## Scaling Calculations

### Capacity Planning

| Bots | Max Users | Throughput | Time for 100k |
|------|-----------|------------|---------------|
| 1    | 5,000     | 1,500/min  | 67 min        |
| 5    | 25,000    | 7,500/min  | 13.3 min      |
| 10   | 50,000    | 15,000/min | 6.7 min       |
| 20   | 100,000   | 30,000/min | 3.3 min       |

### Rate Limit Distribution

Each bot maintains its own rate limit:
- **Per Bot**: 25 msg/sec (safe under 30/s limit)
- **Total Pool**: 25 × 20 = 500 msg/sec
- **Effective**: 30,000 users/minute

## Implementation Steps

### Phase 1: Infrastructure Setup

1. **Create Bot Pool**:
   - Register 20 bots with BotFather
   - Configure tokens in .env
   - Set up webhook endpoints

2. **Update Database**:
   - Run migration for new columns
   - Create indexes for performance

3. **Deploy Services**:
   - Dispatcher service
   - Pool bot services (containerized)
   - Load balancer configuration

### Phase 2: User Migration

1. **Gradual Migration**:
   ```python
   # Assign new users to pool
   if user.created_at > migration_date:
       assign_to_pool_bot(user)
   ```

2. **Bulk Migration**:
   ```python
   # Migrate existing users in batches
   for batch in get_user_batches(1000):
       assign_users_to_pool(batch)
   ```

### Phase 3: Notification System Update

1. **Update Batch Processor**:
   ```python
   def notify_users_multibot(ad_data):
       # Group users by assigned bot
       users_by_bot = group_users_by_bot()
       
       # Send to each bot's queue
       for bot_name, users in users_by_bot.items():
           send_to_bot_queue(bot_name, users, ad_data)
   ```

2. **Update Celery Tasks**:
   ```python
   @celery_app.task
   def send_notification_via_bot(bot_name, user_ids, ad_data):
       bot_config = get_bot_config(bot_name)
       bot = Bot(token=bot_config.token)
       # Process notifications
   ```

## Monitoring & Management

### Bot Health Dashboard

```python
# Real-time monitoring
{
    "total_capacity": 100000,
    "total_users": 85234,
    "overall_utilization": "85.2%",
    "bots": [
        {
            "name": "bot_1",
            "username": "@YourBot_1",
            "current_users": 4821,
            "max_users": 5000,
            "utilization": "96.4%",
            "health": "healthy"
        },
        // ... more bots
    ]
}
```

### Key Metrics

1. **Bot Utilization**: Keep between 70-90%
2. **Message Throughput**: Monitor per bot
3. **Error Rates**: Track failed deliveries
4. **Response Times**: Measure notification delays

## Operational Considerations

### 1. Bot Management

- **Rotation**: Periodically rotate heavily used bots
- **Maintenance**: Take bots offline without service disruption
- **Scaling**: Add new bots when utilization > 90%

### 2. User Experience

- **Seamless Transition**: Users don't notice bot changes
- **Consistent Interface**: All bots share same codebase
- **State Preservation**: User data synced across bots

### 3. Cost Optimization

- **Bot Hosting**: Each bot needs minimal resources
- **Shared Infrastructure**: Common database, Redis, etc.
- **Efficient Routing**: Minimize cross-bot communication

## Security Considerations

1. **Token Management**:
   - Store tokens encrypted
   - Rotate periodically
   - Use environment variables

2. **Access Control**:
   - Dispatcher validates users
   - Pool bots verify assignments
   - Rate limit per user

3. **Data Privacy**:
   - User data centralized
   - Bots have read-only access
   - Audit logging enabled

## Deployment Checklist

- [ ] Register required number of bots with BotFather
- [ ] Configure all bot tokens in .env
- [ ] Update database schema
- [ ] Deploy dispatcher service
- [ ] Deploy pool bot services
- [ ] Configure monitoring
- [ ] Test with small user group
- [ ] Gradual rollout
- [ ] Full migration

## Example Implementation Code

### Dispatcher Bot Handler

```python
@dp.message_handler(commands=['start'])
async def start_dispatcher(message: types.Message):
    user_id = message.from_user.id
    
    # Check if user already assigned
    assignment = get_user_assignment(user_id)
    
    if not assignment:
        # Assign to available bot
        assignment = assign_user_to_bot(user_id)
    
    # Redirect to assigned bot
    bot_username = assignment['bot_username']
    await message.answer(
        f"Вітаємо! Для продовження перейдіть до бота {bot_username}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Перейти до бота",
                url=f"https://t.me/{bot_username[1:]}"
            )
        ]])
    )
```

### Notification Distribution

```python
def distribute_notifications(ad_data, user_ids):
    # Group by assigned bot
    bot_groups = defaultdict(list)
    
    users = User.query.filter(User.id.in_(user_ids)).all()
    for user in users:
        if user.assigned_bot_name:
            bot_groups[user.assigned_bot_name].append(user.id)
    
    # Send to each bot's queue
    for bot_name, bot_user_ids in bot_groups.items():
        celery_app.send_task(
            'notify_via_bot',
            args=[bot_name, bot_user_ids, ad_data],
            queue=f'bot_{bot_name}_queue'
        )
```

## Conclusion

The multi-bot dispatcher architecture provides:
- **20x faster** notification delivery
- **Linear scalability** to millions of users
- **High availability** and fault tolerance
- **Cost-effective** scaling solution

This architecture transforms the notification system from a bottleneck into a competitive advantage, enabling real-time notifications at any scale. 