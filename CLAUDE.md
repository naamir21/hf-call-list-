# Standing rules for this repo

- Run `python -m pytest -q` after every change. Don't move on until it passes.
- Run `python agent.py` before calling anything done; it must exit 0.
- Commit after each working step with a short message.
- Never use `DEATH_EVENT` or `time` as score or ML inputs. `DEATH_EVENT` is the answer key only.
- The nurse sees points and plain reasons, never model probabilities.
- No diagnosis language in the UI. Keep the "prioritisation aid" disclaimer.
- Log any assumption in DECISIONS.md instead of asking.
- All SQL must be parameterised. All API errors return JSON `{error, detail}`.
