# Multi-Bot Architecture Deployment Guide

This guide walks you through deploying the multi-bot dispatcher architecture for scaling to 100,000+ users.

## Prerequisites

1. **Create Telegram Bots**:
   - 1 Dispatcher Bot
   - 20 Pool Bots (or fewer to start)
   - Use BotFather: `/newbot` command

2. **Infrastructure**:
   - PostgreSQL database
   - Redis (2 instances: queue + state)
   - Docker & Docker Compose
   - Sufficient server resources

## Step 1: Configure Bot Tokens

1. Copy the environment template:
   ```bash
   cp docs/env_multibot_template.txt .env
   ```

2. Fill in your bot tokens:
   ```env
   # Dispatcher Bot
   TELEGRAM_DISPATCHER_TOKEN=your_actual_dispatcher_token
   TELEGRAM_DISPATCHER_USERNAME=@YourDispatcherBot

   # Pool Bots
   BOT_POOL_1_TOKEN=your_actual_bot_1_token
   BOT_POOL_1_USERNAME=@YourPropertyBot_1
   # ... continue for all bots
   ```

## Step 2: Database Migration

1. Run the migration script:
   ```bash
   python scripts/migrate_multibot.py
   ```

2. Verify migration:
   ```sql
   SELECT column_name FROM information_schema.columns 
   WHERE table_name = 'users' 
   AND column_name LIKE '%bot%';
   ```

## Step 3: Deploy Services

### Option A: Start with 2 Pool Bots (Testing)

1. Start core services:
   ```bash
   docker-compose up -d postgres redis_queue redis_state
   ```

2. Start dispatcher and 2 flower bots (Orchid & Tulip):
   ```bash
   docker-compose -f docker-compose.multibot.yml up -d \
     dispatcher_bot \
     pool_bot_orchid pool_bot_tulip \
     pool_bot_worker_orchid pool_bot_worker_tulip
   ```

### Option B: Full Deployment (20 Bots)

1. Generate full docker-compose with all 20 bots:
   ```bash
   python scripts/generate_multibot_compose.py --bots 20
   ```

2. Deploy all services:
   ```bash
   docker-compose -f docker-compose.multibot-full.yml up -d
   ```

## Step 4: Verify Deployment

1. Check service health:
   ```bash
   docker-compose -f docker-compose.multibot.yml ps
   ```

2. Monitor logs:
   ```bash
   # Dispatcher logs
   docker logs -f dispatcher_bot

   # Pool bot logs  
   docker logs -f pool_bot_orchid
   ```

3. Test bot assignment:
   - Message `/start` to dispatcher bot
   - Should receive assignment to a pool bot
   - Follow the link to your assigned bot

## Step 5: Monitor System

1. Run the monitoring tool:
   ```bash
   python scripts/monitor_multibot_system.py
   ```

2. Check bot statistics:
   ```bash
   python scripts/monitor_multibot_system.py --once
   ```

Expected output:
```
Multi-Bot System Monitor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Capacity: 100,000 users
Current Users: 0 users
Overall Utilization: 0.0%

Bot Pool Status:
 Bot Name    Username           Users    Capacity  Utilization  Status
 orchid      @hto_de_orchid_bot  0       5,000     0.0%        AVAILABLE
 tulip       @hto_de_tulip_bot   0       5,000     0.0%        AVAILABLE
```

## Step 6: Test Notifications

1. Simulate user assignments:
   ```bash
   python scripts/test_multibot_assignments.py --users 100
   ```

2. Test notification throughput:
   ```bash
   python scripts/test_multibot_notifications.py --users 1000
   ```

## Step 7: Production Configuration

### A. Celery Queue Configuration

Add bot-specific queues to `common/celery_app.py`:
```python
Queue('telegram_bot_bot_1_queue', task_exchange, routing_key='telegram.bot.bot_1'),
Queue('telegram_bot_bot_2_queue', task_exchange, routing_key='telegram.bot.bot_2'),
# ... for each bot
```

### B. Nginx Configuration (if using webhooks)

```nginx
# Dispatcher bot
location /webhook/dispatcher {
    proxy_pass http://dispatcher_bot:8000;
}

# Pool bots
location /webhook/bot_1 {
    proxy_pass http://pool_bot_1:8000;
}
# ... for each bot
```

### C. Monitoring & Alerts

Set up alerts for:
- Bot utilization > 90%
- Failed message delivery > 5%
- Queue length > 1000 messages

## Troubleshooting

### Issue: "All bots at capacity"

**Solution**: Add more bots or increase `MAX_USERS` per bot
```bash
# Edit .env
BOT_POOL_1_MAX_USERS=7500  # Increase from 5000

# Restart services
docker-compose -f docker-compose.multibot.yml restart
```

### Issue: Slow notifications

**Check**:
1. Worker concurrency: Should be 16+ per bot
2. Queue backlogs: `redis-cli llen telegram_bot_orchid_queue`
3. Database connections: Not exhausted

### Issue: Bot not responding

**Debug**:
```bash
# Check bot status
docker logs pool_bot_orchid --tail 100

# Test bot token
curl https://api.telegram.org/bot<TOKEN>/getMe

# Restart specific bot
docker-compose -f docker-compose.multibot.yml restart pool_bot_orchid
```

## Scaling Considerations

### Adding More Bots

1. Register new bot with BotFather
2. Add to .env:
   ```env
   BOT_POOL_21_TOKEN=new_bot_token
   BOT_POOL_21_USERNAME=@YourPropertyBot_21
   ```

3. Add to docker-compose
4. Deploy: `docker-compose up -d pool_bot_rose pool_bot_worker_rose`

### Performance Tuning

- **Database**: Use connection pooling, optimize queries
- **Redis**: Use Redis Cluster for > 200k users
- **Workers**: Scale horizontally with more containers
- **Network**: Use Docker Swarm or Kubernetes for multi-host

## Rollback Plan

If issues arise:

1. Stop multi-bot services:
   ```bash
   docker-compose -f docker-compose.multibot.yml down
   ```

2. Revert to single bot:
   ```bash
   docker-compose up -d telegram_service
   ```

3. Users will need to re-register (data preserved)

## Maintenance

### Weekly Tasks
- Review bot utilization
- Rotate heavily used bots
- Check error rates

### Monthly Tasks
- Audit user distribution
- Performance review
- Capacity planning

## Success Metrics

After deployment, you should see:
- ✅ Notification delivery: 3-5 minutes for 100k users
- ✅ Bot utilization: 70-85% optimal
- ✅ Error rate: < 1%
- ✅ User satisfaction: Instant notifications

## Next Steps

1. **Gradual Migration**: Start with new users
2. **Monitor Closely**: First 48 hours critical
3. **Optimize**: Adjust bot distribution based on usage
4. **Document**: Keep deployment notes for team

---

**Support**: For issues, check logs first, then escalate to team lead. 