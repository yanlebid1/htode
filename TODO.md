# TODO — HTODE Project Roadmap

> Track features, research, and improvements to implement.

---

## Business & Strategy

### European Market Expansion
- [ ] **Competitor analysis (Europe)** — Deep analysis of real estate notification platforms operating in European markets (Germany, Poland, Czech Republic, Spain, etc.). Identify key players, their features, pricing, market share, and gaps.
- [ ] **European market entry plan** — Build a comprehensive plan for entering the European market: target countries, localization requirements, legal/compliance considerations, listing sources, partnership opportunities, go-to-market strategy.

---

## Technical Improvements

### Security — Critical
- [ ] **HTTPS in Nginx** — All traffic between Nginx and upstream services is currently unencrypted. Add TLS termination at the load balancer.
- [ ] **Fix `disable_web_security=True` in Camoufox** — The Camoufox browser pool disables web security for extraction. Must be scoped per-request or removed.

### Security — High Priority
- [ ] **PII encryption at rest** — User phone numbers, Telegram IDs, and email addresses are stored in plaintext in PostgreSQL. Implement column-level encryption.
- [ ] **Row-Level Security (RLS) on PostgreSQL** — Add RLS policies to prevent cross-tenant data access.
- [ ] **Secrets management** — Move credentials out of `.env` files into a proper secrets manager (Vault, AWS Secrets Manager, or Docker secrets).

### Testing & CI
- [ ] **Test coverage gaps** — Scraper, notifier, and dispatcher services need continued test expansion (Phase 3+ test suite).
- [ ] **CI Python version mismatch** — CI runs a different Python version than production Docker images. Pin both to Python 3.10.
- [ ] **Security scanning in CI** — Add `bandit`, `safety`, and `trivy` to the GitHub Actions pipeline.
- [ ] **Integration tests** — Add integration tests with real PostgreSQL.

### Infrastructure — Medium Priority
- [ ] **Timezone consistency** — Mix of `datetime.utcnow()` and `datetime.now(timezone.utc)` across the codebase. Standardize to `datetime.now(timezone.utc)`.
- [ ] **Rate limiting on public endpoints** — WebApp and Camoufox API endpoints lack rate limiting.
- [ ] **CSRF protection** — WebApp endpoints do not verify CSRF tokens.
- [ ] **Network segmentation** — All services share a single Docker network. Segment into frontend/backend/data tiers.
- [ ] **Kubernetes migration** — Docker Compose works for current scale but Kubernetes would provide better autoscaling for the 20-bot fleet.
- [ ] **Batch notification optimization** — Current batching dispatches one Celery task per batch. Consider direct async sends within the worker.

### Code Quality — Low Priority
- [ ] **Import ordering** — Inconsistent import ordering across modules. Add `isort` to pre-commit.
- [ ] **Type annotations** — Many functions lack type annotations, especially in handler code.
- [ ] **Code formatting enforcement** — No enforced formatter. Add `black` or `ruff format` to CI.
