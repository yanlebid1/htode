# TODO — HTODE Project Roadmap

> Track features, research, and improvements to implement.

---

## Business & Strategy

### European Market Expansion
- [ ] **Competitor analysis (Europe)** — Deep analysis of real estate notification platforms operating in European markets (Germany, Poland, Czech Republic, Spain, etc.). Identify key players, their features, pricing, market share, and gaps.
- [ ] **European market entry plan** — Build a comprehensive plan for entering the European market: target countries, localization requirements, legal/compliance considerations, listing sources, partnership opportunities, go-to-market strategy.

---

## Technical Improvements

### Security (Critical)
- [ ] Enable HTTPS in Nginx
- [ ] Fix `disable_web_security=True` in Camoufox
- [ ] PII encryption at rest
- [ ] Row-level security (RLS) on PostgreSQL
- [ ] Secrets management (vault/sealed secrets)

### Testing & CI
- [ ] Increase test coverage for scraper/notifier/dispatcher services
- [ ] Fix CI Python version mismatch
- [ ] Add security scanning to CI pipeline (Bandit, Safety)
- [ ] Add integration tests with real PostgreSQL

### Infrastructure
- [ ] Timezone consistency across services
- [ ] Rate limiting middleware
- [ ] CSRF protection
- [ ] Network segmentation in Docker
- [ ] Kubernetes migration plan
- [ ] Batch notification optimization

### Code Quality
- [ ] Import ordering enforcement (isort)
- [ ] Type annotations for core modules
- [ ] Code formatting enforcement (black/ruff)
