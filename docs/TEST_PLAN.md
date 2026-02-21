# Test Infrastructure Overhaul & Implementation Plan

## Context

The test suite is broken and provides ~3% coverage. CI fails on every run (`requirements-dev.txt` missing). 3 of 7 test files have broken imports/mocks from stale code paths. 2 files aren't even pytest tests. This plan fixes everything and adds ~90 new tests targeting the highest-value modules, bringing coverage to ~40%.

---

## Phase A: Fix CI & Test Infrastructure

### A1. Create `requirements-dev.txt`
Aggregates project deps + test deps so CI can install everything.

### A2. Fix `.github/workflows/test.yml`
- Fix the broken `pip install -r requirements-dev.txt` reference
- Add `--cov=system` to coverage targets
- Add PostgreSQL service for future integration tests

### A3. Rewrite `tests/conftest.py`
- **Remove** `load_dotenv()` — set test env vars via `os.environ.setdefault()` before any imports
- **Remove** broken fixtures: `mock_redis` (patches wrong target), `mock_db_connection`, `mock_execute_query` (patch legacy paths), `event_loop` (deprecated)
- **Add** SQLite in-memory `db_engine` / `db_session` fixtures (selective table creation to avoid PostgreSQL ARRAY issues)
- **Add** `mock_cache_managers` fixture to prevent Redis calls from repository decorators
- **Keep** `test_ad_data` fixture (useful), remove unused `test_user_id`

### A4. Move non-test scripts out of `tests/`
- `tests/test_adspower_popup_handling.py` → `scripts/`
- `tests/test_adspower_integration.py` → `scripts/`

### A5. Update `pytest.ini`
- Add `asyncio_mode = auto` to eliminate manual `@pytest.mark.asyncio` decorators
- Add `filterwarnings` to suppress deprecation noise

---

## Phase B: Fix Existing Broken Tests

### B1. Rewrite `tests/test_maintenance.py` (5 tests)
**Problem:** Imports `is_ad_inactive`, `get_ad_images`, `delete_ad` from `system.maintenance` — these don't exist after Phase 2 split.
**Fix:** Test actual exports (`cleanup_old_ads`, `cleanup_expired_verification_codes`) by mocking `db_session`, `AdRepository`, `AdService` at `system.maintenance.cleanup.*`.

### B2. Rewrite `tests/test_state_manager.py` (5 tests)
**Problem:** Mocks `redis.from_url` but `StateManager` uses `get_state_redis()` from cluster manager.
**Fix:** Patch `common.utils.redis_cluster_manager.get_state_redis` to return a `MagicMock` Redis, or use `fakeredis`.

### B3. Fix `tests/test_telegram_service.py` (5 tests)
**Problem:** Tests 2-3 test retry behavior (`retry_count`, `retry_delay`) that doesn't exist in `safe_send_message`.
**Fix:** Remove the 2 broken retry tests. Add `test_safe_send_message_failure_returns_none` and `test_safe_send_photo_fallback_on_error`.

### B4. Keep `tests/test_mini_webapp.py` (7 tests) — working, no changes needed.

---

## Phase C: New Test Files (priority order)

### C1. `tests/test_config.py` — Config & Constants (12 tests)
Pure function tests, no mocks needed.
- `build_ad_text()`: plain, markdown, geo_id lookup, missing fields, unknown city
- `get_key_by_value()`: found, not found
- `GEO_ID_MAPPING`: contains expected cities
- Constants: `FREE_TRIAL_DAYS`, `NOTIFICATION_BATCH_SIZE`, values are positive ints

### C2. `tests/test_distributed_lock.py` — Concurrency (10 tests)
Mock Redis client. Tests:
- `acquire()` success/failure (redis.set returns True/None)
- `release()` success/failure/without-token (redis.eval returns 1/0)
- Sync context manager (`with lock:`) — success + `LockNotAcquired`
- Async context manager (`async with lock:`) — success + `LockNotAcquired`
- Unique token per acquire

### C3. `tests/test_webcrawler.py` — SSRF Protection (15 tests)
Direct function tests + TestClient.
- `_is_private_ip()`: 127.0.0.1, 10.x, 192.168.x, public IP, hostname
- `validate_url()`: valid http/https, blocked schemes (ftp/file), localhost, metadata endpoint (169.254.169.254), private IPs
- Endpoints: GET /health, POST /crawl with invalid URL, POST /crawl with valid structure (mock fetch)

### C4. `tests/test_repositories.py` — Repository Layer (30 tests)
In-memory SQLite via `db_session` fixture. Mock cache managers. Selective table creation (skip `user_filters` table — uses PostgreSQL ARRAY).

**UserRepository (10):** create, get_by_id (found/not found), get_by_messenger_id, get_by_phone, get_by_email, get_or_create (new/existing), start_free_subscription, get_subscription_status

**AdRepository (10):** create, create duplicate, get_by_id, get_by_external_id, get_by_resource_url, update, delete, filter by price, add_image, add_phone

**FavoriteRepository (5):** add, add duplicate, add exceeds 50 limit, remove, list

**PaymentRepository (5):** create, get_by_order_id, update_status, filter by status, cleanup expired

### C5. `tests/test_payment.py` — Payment Signature (8 tests)
Set env vars for merchant credentials. Pure function tests.
- `generate_signature()`: deterministic, changes with data, key ordering
- `create_payment_request()`: correct structure, includes signature
- Signature verification: valid/invalid/wrong status

### C6. `tests/test_bot_assignment.py` — Bot Assignment (8 tests)
Mock `multibot_config` and `DistributedLock`. Note: `get_bot_user_counts` filters on nonexistent `User.is_active` — mock it at method level.
- `find_available_bot()`: returns least loaded, all at capacity → None, no bots → None
- `assign_user_to_bot()`: success, no available bot, lock not acquired
- `get_user_bot_assignment()`: user with/without assignment
- `get_bot_statistics()`: correct structure

### C7. `tests/test_camoufox_service.py` — Health & Pool (6 tests)
Mock `browser_pool` to avoid real browser init.
- Pool stats: initial state, after requests, success rate calculation
- Health endpoint: 503 when not initialized, 200 when healthy
- `BrowserRequest` Pydantic validation: valid/invalid inputs

---

## SQLite Compatibility Strategy

PostgreSQL `ARRAY(Integer)` on `UserFilter.rooms_count` breaks SQLite. Solution: **selective table creation** — only create tables needed per test fixture, skipping `user_filters`. `SubscriptionRepository` tests deferred to Phase 2 (needs real PostgreSQL).

`Payment.payment_details` uses `JSON` — works fine with SQLAlchemy's SQLite dialect.

---

## Files Modified/Created

| Action | File |
|--------|------|
| Create | `requirements-dev.txt` |
| Edit | `.github/workflows/test.yml` |
| Rewrite | `tests/conftest.py` |
| Edit | `pytest.ini` |
| Move | `tests/test_adspower_popup_handling.py` → `scripts/` |
| Move | `tests/test_adspower_integration.py` → `scripts/` |
| Rewrite | `tests/test_maintenance.py` |
| Rewrite | `tests/test_state_manager.py` |
| Fix | `tests/test_telegram_service.py` |
| Create | `tests/test_config.py` |
| Create | `tests/test_distributed_lock.py` |
| Create | `tests/test_webcrawler.py` |
| Create | `tests/test_repositories.py` |
| Create | `tests/test_payment.py` |
| Create | `tests/test_bot_assignment.py` |
| Create | `tests/test_camoufox_service.py` |

## Expected Outcome

| Metric | Before | After |
|--------|--------|-------|
| Pytest-compatible tests | 24 (many broken) | ~111 (all passing) |
| Broken test files | 4/7 | 0 |
| CI status | Broken | Green |
| Estimated coverage | ~3% | ~40% |
| Services with tests | 2/8 | 4/8 |
| Repository coverage | 0% | ~70% |

## Verification
```bash
# After implementation:
pytest tests/ -v                    # All tests pass
pytest tests/ --co                  # Collection shows ~111 tests
pytest tests/ --cov=common --cov=services --cov=system  # Coverage report
```
