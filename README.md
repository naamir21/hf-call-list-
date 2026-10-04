# Heart-failure call list

Ranks 299 discharged heart-failure patients so a nurse knows who to call first.
Transparent points score, compared against the "oldest first" default.
IEEE YP Industry Hackathon 2026, Case 2.

## Run it

```bash
pip install -r requirements.txt
python agent.py                 # builds the DB, runs everything, checks itself, writes RESULTS.md
uvicorn app:app --reload        # then open http://127.0.0.1:8000
```

Sign in as `nurse` / `nurse-demo-1` or `manager` / `manager-demo-1`.
Managers can save the default weight and open the audit log.

Other commands:

```bash
python db.py          # rebuild patients.db from data/
python ml_check.py    # logistic-regression check of the weights
python -m pytest -q   # 46 tests
```

API docs: http://127.0.0.1:8000/docs

## The score

2 points for low ejection fraction (< 35%), 2 for high serum creatinine (> 1.5 mg/dL),
1 each for anaemia, diabetes and high blood pressure, and 1 for age 70 or over.
Ties go to lower EF, then higher creatinine. The "weak heart and kidney weight" slider
changes the 2s.

## Files

| File | Job |
|---|---|
| `scoring.py` | Points, reasons, ranking, oldest-first baseline |
| `db.py` | Load CSV, validate, clean, SQLite tables |
| `evaluation.py` | Deaths in top 25, overlap, who rose/fell |
| `ml_check.py` | Logistic regression check (not used by the app) |
| `auth.py` | Password hashing, signed tokens, demo users |
| `app.py` | REST API, roles, audit log, CSV export |
| `static/index.html` | Dashboard |
| `agent.py` | One-command pipeline with self-checks |
| `RESULTS.md` | Real numbers and the story for the judges |

## API

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /api/login` | anyone | Returns token |
| `GET /api/calllist?hi=&strategy=risk\|oldest` | nurse, manager | Top 25 with reasons |
| `GET /api/compare?hi=&hi_revise=` | nurse, manager | Baseline vs v1 vs revised |
| `GET/PUT /api/weights` | read: all, write: manager | Default weights |
| `GET /api/audit` | manager | Audit log |
| `GET /api/export.csv` | nurse, manager | Download the list |
| `GET /api/status` | nurse, manager | Cleaning report and active weights |

## Demo script

1. "We ranked 299 patients (0 dropped) and picked the top 25 a nurse should call."
2. "Oldest-first caught 18 deaths; our risk score caught 19, and 20 with the heavier weight."
3. "The two lists share only 2 patients, so the score picks very different people."
4. "Raising the weight from 2 to 3 kept 22 of 25. The 3 who joined all have both a weak pump and struggling kidneys."
5. "A logistic regression agreed that ejection fraction and creatinine matter most (AUC 0.77)."
6. "We ranked who looks riskiest on paper. We did not diagnose anyone."

## Known limitations

- Small, retrospective dataset (299 patients). A 1–2 death difference could be chance.
- The ML check suggests age 70+ deserves more than 1 point. We kept the design's weights and report this openly in RESULTS.md.
- No rate limiting on login, no MFA, no HTTPS in the dev server. Put it behind a TLS proxy for anything real.
- Demo passwords are public. Change them with env vars.
- SQLite is fine for one clinic laptop, not for many users at once.
- Not validated prospectively. Not a medical device.
