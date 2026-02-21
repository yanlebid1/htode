# CLAUDE.md — Project Intelligence for HTODE

> This file is the single source of truth for AI assistants working on this codebase.
> It is automatically loaded into context at the start of every conversation.

---

## Project Overview

**HTODE** is a distributed multi-bot real estate notification platform for the Ukrainian market. It scrapes property listings from OLX, DomRia, Flatfy, LUN, and other sources, then delivers personalized notifications to 100,000+ users via Telegram using a fleet of 20 flower-themed bots.

**Core value prop:** 20 bots × 1,500 msgs/min = 30,000 msgs/min → 100K users notified in ~3.3 minutes (vs 67 min single-bot).

**Language:** Python 3.10 | **Framework:** Aiogram 3.17.0 (Telegram), FastAPI (web) | **Queue:** Celery + Redis | **DB:** PostgreSQL via SQLAlchemy + PgBouncer | **Infra:** Docker Compose

---

## Architecture

### Services (8 microservices)

| Service | Dir | Purpose | Entry Point |
|---------|-----|---------|-------------|
| **Dispatcher** | `services/dispatcher_service/` | User entry point, assigns to pool bots | `app/main.py` → `asyncio.run(dp.start_polling(bot))` |
| **Pool Bot (×20)** | `services/pool_bot_service/` | Individual flower bots, reuses telegram_service handlers | `app/main.py` → `asyncio.run(dp.start_polling(bot))` |
| **Telegram** | `services/telegram_service/` | Core bot logic: handlers, payments, subscriptions, states | `app/main.py` → `asyncio.run(dp.start_polling(bot))` |
| **Scraper** | `services/scraper_service/` | Web scraping of listings | `app/tasks.py` → Celery `fetch_new_ads` |
| **Notifier** | `services/notifier_service/` | Matches ads to user filters, batch dispatch | `app/tasks.py` → Celery `sort_and_notify_new_ads` |
| **Webcrawler** | `services/webcrawler_service/` | HTTP-only crawling with proxy support | `app/main.py` → FastAPI |
| **Camoufox** | `services/camoufox_service/` | Headless browser automation (anti-detection) | `app/main.py` → FastAPI with browser pool |
| **WebApps** | `services/webapps/` | Telegram Mini App endpoints (gallery, phones) | `mini_webapp.py` → FastAPI (3 replicas) |

### Aiogram v3 Handler Pattern

The codebase uses **aiogram 3.17.0** with the Router pattern:

```python
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

@router.message(Command("start"))
async def start_handler(message: types.Message):
    ...

@router.callback_query(F.data.startswith("prefix_"))
async def callback_handler(callback_query: types.CallbackQuery):
    ...
```

- Each handler module creates its own `Router()` instance
- Routers are registered with `dp` via `dp.include_routers(...)` in each service's `main.py`
- Pool bot service imports and registers telegram_service's routers with its own dispatcher
- Keyboards use `InlineKeyboardMarkup(inline_keyboard=[[btn1, btn2], [btn3]])` constructor (no `.add()`/`.row()`)
- States: `await state.set_state(MyState.waiting)` / `await state.clear()`
- Exceptions: `from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, ...`

### Shared Code (`common/`)

| Module | Purpose |
|--------|---------|
| `common/db/` | SQLAlchemy models (`models/`), repositories (`repositories/`), session management |
| `common/messaging/` | Unified messaging interface, Celery tasks, multibot dispatch, keyboard utils, `keyboard_helpers.py` |
| `common/services/` | `BotAssignmentService` (load balancing), `UserService`, `AdService` |
| `common/utils/` | Phone extraction (`phone_utils/`), caching, Redis cluster mgmt, distributed locks, S3, logging |
| `common/flows/` | Property search flow, subscription flow (multi-step FSM) |
| `common/verification/` | Email, phone, SMS verification |
| `common/config.py` | DB config, AWS config, geo mappings, `WEBAPP_URL`, `build_ad_text()` |
| `common/constants.py` | All magic numbers: `FREE_TRIAL_DAYS`, `NOTIFICATION_BATCH_SIZE`, etc. |
| `common/celery_app.py` | Celery config, queue definitions, rate limits, task routing |

### Infrastructure

| Component | Details |
|-----------|---------|
| **PostgreSQL** | Primary DB, schema in `init.sql` |
| **PgBouncer** | Connection pooling (300 connections) |
| **Redis ×4** | `redis_queue` (Celery broker), `redis_cache`, `redis_state` (FSM), `redis_analytics` |
| **Redis Sentinel ×3** | HA failover for Redis |
| **Nginx** | HTTPS load balancer (TLS 1.2/1.3) for webapp, camoufox, webcrawler |
| **Prometheus + Grafana** | Metrics and dashboards |
| **Loki + Promtail** | Centralized log aggregation |
| **Jaeger** | Distributed tracing via OpenTelemetry |

### Data Flow

```
Scraper → fetch listings → Insert to DB → Notifier matches users
→ Group by assigned bot → Queue per bot → Pool Bot sends via Telegram API
```

### Multi-Bot Pattern

```
New User → Dispatcher Bot → BotAssignmentService.find_available_bot()
→ Assigns to least-loaded flower bot → All future comms via that bot
```

---

## Development Conventions

### Code Style

- **Structured logging everywhere** — use `logger.info("msg", extra={...})`, never f-strings in log calls
- **Repository pattern** for DB access — `UserRepository`, `AdRepository`, etc. in `common/db/repositories/`
- **Session context manager** — always `with db_session() as db:` for DB operations
- **Constants in `common/constants.py`** — no magic numbers in business logic
- **Distributed locks** — use `DistributedLock` from `common/utils/distributed_lock.py` for concurrency
- **Celery tasks** — define in `tasks.py` per service, register in `common/messaging/task_registry.py`
- **aiogram v3 Router pattern** — each handler module has its own `Router()`, registered in `main.py`

### File Organization

- Each service is self-contained under `services/<name>/`
- Shared logic goes in `common/` — never duplicate across services
- Pool bot service reuses `telegram_service` handler routers via `dp.include_routers()`
- Docker configs: `docker-compose.yml` (main), `docker-compose.multibot.yml` (2-bot test), `docker-compose.multibot-full.yml` (20-bot prod)

### Naming Conventions

- **Flower bots**: orchid, tulip, daisy, lavender, jasmine, sunflower, lotus, peony, violet, azalea, clover, marigold, bluebell, gardenia, aster, hibiscus, freesia, verbena, hyacinth, fuchsia
- **Bot usernames**: `@hto_de_{flower}_bot`
- **Celery queues**: `telegram_bot_{flower}_queue` per bot
- **Redis keys**: `user_state:{telegram_id}`, `user_context:{telegram_id}`, `lock:{resource}`
- **DB tables**: `users`, `ads`, `ad_images`, `ad_phones`, `user_filters`, `subscriptions`, `favorite_ads`, `payment_orders`

### Environment Variables

Critical env vars (must be in `.env`):
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_PGBOUNCER_HOST`
- `REDIS_QUEUE_URL`, `REDIS_CACHE_URL`, `REDIS_STATE_URL`, `REDIS_ANALYTICS_URL`
- `TELEGRAM_DISPATCHER_TOKEN`, `BOT_POOL_1_TOKEN` through `BOT_POOL_20_TOKEN`
- `WEBAPP_URL` — **required**, no fallback (logs warning if unset)
- `WAYFORPAY_MERCHANT_LOGIN`, `WAYFORPAY_MERCHANT_SECRET`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `CLOUDFRONT_DOMAIN`

### Key Config Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Main orchestration (~1400 lines) |
| `init.sql` | Database schema + indexes |
| `nginx.conf` | HTTPS load balancer config (TLS termination) |
| `ssl/generate-dev-certs.sh` | Generate self-signed certs for local dev |
| `redis-sentinel.conf` | Redis HA config |
| `monitoring/prometheus.yml` | Scrape targets |
| `monitoring/loki.yml` | Log aggregation config |
| `.github/workflows/test.yml` | CI pipeline |

---

## Working with This Codebase

### Common Tasks

**Adding a new Telegram handler:**
1. Create handler file in `services/telegram_service/app/handlers/`
2. Define `router = Router()` and decorate handlers with `@router.message()` / `@router.callback_query()`
3. Import and register the router in `services/telegram_service/app/main.py` via `dp.include_routers()`
4. If it needs state, add FSM states to `app/states/` using `from aiogram.fsm.state import State, StatesGroup`
5. Pool bots automatically inherit it (routers are imported in `pool_bot_service/app/main.py`)

**Adding a new scraper source:**
1. Create parser in `common/utils/phone_utils/parsers/`
2. Register in `ExtractionClient` (`common/utils/extraction_client.py`)
3. Add scrape task to `services/scraper_service/app/tasks.py`

**Adding a Celery task:**
1. Define in relevant service's `tasks.py`
2. Add queue routing in `common/celery_app.py`
3. Set appropriate rate limits and time limits

**Modifying Docker infrastructure:**
1. Edit `docker-compose.yml` for the main stack
2. Keep `docker-compose.multibot.yml` in sync for testing
3. Add healthchecks with `start_period` for any new service

### Critical Paths to Be Careful With

- **`common/celery_app.py`** — rate limits and queue routing; wrong values = Telegram ban or queue starvation
- **`common/services/bot_assignment_service.py`** — uses distributed lock; changes can cause race conditions
- **`common/unified_state_management.py`** — uses atomic Lua scripts; test any changes thoroughly
- **`services/telegram_service/app/payment/wayforpay.py`** — HMAC signing; uses `hmac.compare_digest()` for timing-safe comparison
- **`docker-compose.yml`** — anchor-based inheritance (`x-common-variables`, `x-combined-env`); changes propagate to all services
- **`nginx.conf`** — TLS termination; cert files expected at `ssl/fullchain.pem` and `ssl/privkey.pem`

### Testing

```bash
# Run all tests (702 tests)
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_telegram_service.py -v

# Run with coverage
python -m pytest tests/ --cov=common --cov=services -v
```

**Test files:** 40+ test files in `tests/` covering all services, common utilities, messaging, repositories, handlers, and more.

**Load test scripts:** `scripts/test_ultra_fast_notifications.py`, `scripts/test_*_load.py`

**CI:** GitHub Actions (`.github/workflows/test.yml`) — runs on push to main/develop and PRs

### Monitoring

```bash
# Multi-bot system overview
python scripts/monitor_multibot_system.py

# Service-specific
python scripts/monitor_browser_pool.py
python scripts/monitor_redis_cluster.py
python scripts/monitor_db_connections.py
```

Grafana dashboards at `localhost:3000` when monitoring stack is running.

---

## Technical Debt & Audit Status

A comprehensive technical audit was performed (see `docs/TECHNICAL_AUDIT_2026_02.md`). **All 25 original debt items are resolved.** Phases 1-12 of remediation are complete.

### Completed (Phases 1-9)
- SSRF prevention, SQL injection fix, XSS fix, timing-attack fix
- Redis authentication on all instances
- Removed all hardcoded credentials and ngrok URLs
- `KEYS` → `SCAN` in Redis operations
- Non-root containers in all Dockerfiles, pinned base images
- Race condition fixes (bot assignment, state management) via distributed locks + Lua scripts
- `maintenance.py` monolith split into 5 modules
- Constants centralized, ad text formatting deduplicated
- Deterministic Redis DB selection (`hashlib` instead of `hash()`)
- PgBouncer connection pooling, materialized views, right-sized Celery concurrency
- Prometheus + Grafana + Loki + Jaeger observability stack
- Celery time limits, dead letter queue, security headers
- Structured logging across entire codebase
- Dependency pinning, Docker hardening, input validation on camoufox/webapp
- HTTP timeouts on external API calls, pool-aware health endpoints
- HTTPS in Nginx with TLS 1.2/1.3, HSTS, modern ciphers
- Removed `disable_web_security=True` from Camoufox browser instances
- All vulnerable dependencies updated — **0 Dependabot alerts** (was 120)
- Migrated aiogram v2 → v3 (3.17.0) with Router pattern across all services
- 702 unit tests across all services (was near-zero on many)

### Completed (Security Hardening)
- **Security scanning in CI** — bandit (static analysis) + pip-audit (dependency vulnerabilities) run as parallel GitHub Actions job
- **Timezone consistency** — all `datetime.now()` / `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` across ~35 files
- **PII encryption at rest** — Fernet (AES) encryption + HMAC-SHA256 search tokens for user email/phone via `common/utils/encryption.py`; requires `ENCRYPTION_MASTER_KEY` and `ENCRYPTION_HMAC_KEY` env vars; migration script at `scripts/migrate_pii_encryption.py`
- **Secrets management** — Docker Secrets with env var fallback via `common/utils/secrets.py`; `get_secret()` used for DB password, bot tokens, payment secrets, SMTP password, AWS secret key, encryption keys; 27 secrets defined in `docker-compose.yml`
- **CSRF / Web hardening** — Content-Security-Policy header in nginx; Telegram WebApp guard on mini app HTML templates; `validate_telegram_init_data()` HMAC-SHA256 validation for server-side auth
- **Docker network segmentation** — flat `app_net` replaced with 4 networks: `data_net` (DB/Redis), `edge_net` (nginx/webapps/camoufox/webcrawler), `worker_net` (scrapers/phone workers → camoufox/webcrawler), `monitoring_net` (Prometheus/Grafana/Loki/Jaeger); data-layer ports removed from production; `docker-compose.override.yml` re-exposes for dev

### Completed (Phase 12 — RLS, Batch Tuning, Backup)
- **Row-Level Security** — RLS on 6 user-owned tables with dual-policy pattern (user + system bypass); `rls_session(user_id)` context manager; migration script at `scripts/migrate_rls.py`
- **Batch notification tuning** — `NOTIFICATION_BATCH_SIZE` 100→250, rate limit 15/m→25/m; Redis dedup prevents duplicate notifications (24h TTL)
- **PostgreSQL backup** — daily `pg_dump -Fc` → S3 via `system.maintenance.backup_database` at 2 AM UTC; weekly cleanup of old backups; `scripts/restore_backup.py` for manual restore

### Remaining (low priority)
- Kubernetes migration (future)

---

## Superpowers & Advanced Skills

When working on this project, leverage Claude's advanced capabilities:

### Brainstorming (`/brainstorm`)
Use for architectural decisions, scaling strategies, and creative problem-solving:
- "How should we implement blue-green deployments for 20 bots?"
- "What's the best approach to add PII encryption without downtime?"
- "Design a rate-limiting strategy that respects per-bot Telegram limits"

### Think (`/think`)
Use for complex debugging, race condition analysis, and multi-service interactions:
- Trace request flows across all 8 services
- Analyze Celery task chains and failure modes
- Reason about concurrent state mutations in Redis

### Code Review
Use for reviewing PRs, especially changes touching:
- Celery task definitions (rate limits, retries, routing)
- Redis operations (atomicity, key naming, TTL)
- Database queries (N+1, missing indexes, connection leaks)
- Docker config (resource limits, healthchecks, network)

### Planning (`/plan`)
Use before any multi-file change:
- New feature implementation across services
- Infrastructure changes (adding services, changing Redis topology)
- Refactoring that touches `common/` (affects all services)

### Memory
This project uses Claude's auto-memory at `~/.claude/projects/-home-lyk-projects-htode/memory/`. Key decisions and patterns discovered during work are persisted across sessions.

---

## Quick Reference

### Service Ports

| Service | Internal Port | External Port |
|---------|--------------|---------------|
| PostgreSQL | 5432 | 5432 |
| PgBouncer | 6432 | 6432 |
| Redis Queue | 6379 | 6379 |
| Redis State | 6379 | 6381 |
| Redis Analytics | 6379 | 6382 |
| Webcrawler | 8200 | 9243 (HTTPS) |
| Camoufox | 8100 | 9143 (HTTPS) |
| WebApp | 8080 | 443 (HTTPS) |
| Prometheus | 9090 | 9090 |
| Grafana | 3000 | 3000 |
| Nginx LB | 80/443 | 80 (redirect), 443 (HTTPS) |
| Nginx Monitoring | 8888 | 8888 |

### Celery Queues (by priority)

| Queue | Priority | Rate Limit | Service |
|-------|----------|------------|---------|
| `scraper_queue` | 10 | 1/min | scraper |
| `priority_queue` | 9 | — | cross-service |
| `phone_extraction_queue` | 5 | — | scraper |
| `telegram_queue` | 3 | 20/s | telegram |
| `maintenance_queue` | 2 | 1/h | system |
| `notification_queue` | 1 | 25/s | notifier |
| `telegram_bot_{flower}_queue` | — | 25/s each | pool bots |

### Ukrainian Cities (GEO_ID_MAPPING)

Kyiv, Lviv, Dnipro, Odesa, Kharkiv, Vinnytsia, Zhytomyr, Zaporizhzhia, Ivano-Frankivsk, Kropyvnytskyi, Lutsk, Mykolaiv, Poltava, Rivne, Sumy, Ternopil, Uzhhorod, Khmelnytskyi, Cherkasy, Chernihiv
