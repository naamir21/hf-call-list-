# Plan

## Architecture
One FastAPI service (small monolith) with a SQLite file and a static page.

```
CSV -> db.py (validate, clean) -> patients.db
                                    |
scoring.py (points + reasons) <-----+
evaluation.py (baseline vs v1 vs revised)
auth.py (hashed passwords, signed tokens, roles)
app.py (REST API + audit log) -> static/index.html
ml_check.py (logistic regression check, separate from app)
agent.py (runs the whole pipeline end to end, writes RESULTS.md)
```

## Tasks
| # | Task | Priority | Status |
|---|------|----------|--------|
| 1 | Ingestion + cleaning with report | Must | done |
| 2 | Points score + reasons + tie-breaks | Must | done |
| 3 | Top 25 vs oldest-first, deaths captured | Must | done |
| 4 | hi 2 -> 3 compare: overlap, rose/fell | Must | done |
| 5 | SQLite tables (patient, weight_config, score_result, user, audit_log) | Should | done |
| 6 | ML check (logistic regression, 5-fold CV) | Should | done |
| 7 | API + web page | Should | done |
| 8 | Login (nurse/manager), audit log, CSV export, risk pills | Nice | done |
| 9 | Autonomous pipeline runner (agent.py) + RESULTS.md | Extra | done |
| 10 | QA, review, security pass | Must | done |
