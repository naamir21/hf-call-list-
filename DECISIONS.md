# Decisions and assumptions

1. **Python 3.12 tested** (guide asks for 3.10+). Nothing 3.12-only is used.
2. **Passwords use PBKDF2-SHA256 (standard library), not bcrypt.** Same job, no extra install. Swap to bcrypt/argon2 for production.
3. **Tokens are HMAC-signed and last 8 hours (one shift).** Set `HF_SECRET` so tokens survive a restart; without it a random key is made each start (safe default).
4. **Demo accounts** `nurse` / `nurse-demo-1` and `manager` / `manager-demo-1` are created on first start. Override with `HF_NURSE_PASSWORD` and `HF_MANAGER_PASSWORD`.
5. **`extra`, `age_cut`, `age_pts` from the design's weight config are supported** in the API and DB. The UI only exposes `hi`, as the design asks.
6. **Range checks** (EF 5–100, creatinine 0.1–20, age 0–120, sodium 90–180, flags 0/1) decide what is "out of range". The real data passes all of them: 0 dropped.
7. **Final tie-break is patient_id** (after score, lower EF, higher creatinine) so the list is the same every time. Oldest-first also breaks age ties by patient_id.
8. **Risk colour** is relative to the highest possible score for the current weights: high ≥ 50%, medium ≥ 25%, else low. Every patient in the risk top 25 is "high", which is honest; the colours vary more in the oldest-first view.
9. **Slider range is 1–5** (design asks for at least 2–3). Compare panel always shows the saved default vs the slider value.
10. **"Deaths in top 25" for the ML ranking uses out-of-fold probabilities** so the model is never graded on patients it trained on. It is shown for reference only; the app never uses the model.
11. **`agent.py` is the "autonomous" piece:** one command rebuilds the data, runs every step, checks the acceptance criteria and writes RESULTS.md. It exits 1 on any failed check so it can run unattended.
12. **Frontend uses no external fonts or scripts** so it works offline and the content-security policy can stay strict.
13. `sex`, `smoking`, `platelets`, `serum_sodium`, `creatinine_phosphokinase` are stored but not scored, per the guide. `time` and `DEATH_EVENT` are never scored or shown.
