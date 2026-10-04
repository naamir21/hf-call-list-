"""Points-based risk score. Pure functions: (patients, weights) -> ranked list.

score = hi*(EF < 35) + hi*(creatinine > 1.5)
      + extra*(anaemia + diabetes + high_blood_pressure)
      + age_pts*(age >= age_cut)

DEATH_EVENT and time are never used here.
"""
from dataclasses import dataclass, asdict
import math

import pandas as pd

EF_CUT = 35          # ejection fraction below this = weak pump
CREAT_CUT = 1.5      # serum creatinine above this = kidneys struggling
TOP_N = 25

SCORE_INPUTS = ["age", "ejection_fraction", "serum_creatinine",
                "anaemia", "diabetes", "high_blood_pressure"]


class WeightError(ValueError):
    pass


@dataclass(frozen=True)
class Weights:
    hi: float = 2          # weak heart (EF) and kidney (creatinine) points
    extra: float = 1       # anaemia, diabetes, high blood pressure points
    age_cut: int = 70
    age_pts: float = 1

    def __post_init__(self):
        for name in ("hi", "extra", "age_pts"):
            v = getattr(self, name)
            if not isinstance(v, (int, float)) or isinstance(v, bool) \
                    or math.isnan(v) or math.isinf(v) or v < 0 or v > 100:
                raise WeightError(f"{name} must be a number from 0 to 100, got {v!r}")
        if not isinstance(self.age_cut, int) or isinstance(self.age_cut, bool) \
                or not 0 <= self.age_cut <= 120:
            raise WeightError(f"age_cut must be a whole number from 0 to 120, got {self.age_cut!r}")

    def as_dict(self):
        return asdict(self)


def _num(x):
    """Return int when the value is whole, so scores print as 7 not 7.0."""
    x = float(x)
    return int(x) if x.is_integer() else round(x, 2)


def score_patients(df: pd.DataFrame, w: Weights = Weights()) -> pd.DataFrame:
    missing = [c for c in SCORE_INPUTS if c not in df.columns]
    if missing:
        raise KeyError(f"Missing columns for scoring: {missing}")
    out = df.copy()
    out["score"] = (
        (out["ejection_fraction"] < EF_CUT).astype(float) * w.hi
        + (out["serum_creatinine"] > CREAT_CUT).astype(float) * w.hi
        + (out["anaemia"] + out["diabetes"] + out["high_blood_pressure"]).astype(float) * w.extra
        + (out["age"] >= w.age_cut).astype(float) * w.age_pts
    )
    return out


def rank(scored: pd.DataFrame) -> pd.DataFrame:
    """Sort by score desc, then lower EF, then higher creatinine, then patient_id (stable)."""
    cols, asc = ["score", "ejection_fraction", "serum_creatinine"], [False, True, False]
    if "patient_id" in scored.columns:
        cols.append("patient_id"); asc.append(True)
    out = scored.sort_values(cols, ascending=asc, kind="mergesort").reset_index(drop=True)
    out["rank"] = out.index + 1
    return out


def top_n(scored: pd.DataFrame, n: int = TOP_N) -> pd.DataFrame:
    return rank(scored).head(n)


def oldest_first(df: pd.DataFrame, n: int = TOP_N) -> pd.DataFrame:
    cols, asc = ["age"], [False]
    if "patient_id" in df.columns:
        cols.append("patient_id"); asc.append(True)
    return df.sort_values(cols, ascending=asc, kind="mergesort").head(n).reset_index(drop=True)


def reasons(row, w: Weights = Weights()) -> list[str]:
    r = []
    if row["ejection_fraction"] < EF_CUT: r.append("Low ejection fraction")
    if row["serum_creatinine"] > CREAT_CUT: r.append("High creatinine")
    if row["anaemia"]: r.append("Anaemia")
    if row["diabetes"]: r.append("Diabetes")
    if row["high_blood_pressure"]: r.append("High blood pressure")
    if row["age"] >= w.age_cut: r.append(f"Age {w.age_cut}+")
    return r


def risk_band(score: float, w: Weights = Weights()) -> str:
    """Colour band relative to the highest possible score for these weights."""
    max_score = 2 * w.hi + 3 * w.extra + w.age_pts
    if max_score == 0:
        return "low"
    frac = score / max_score
    if frac >= 0.5:
        return "high"
    if frac >= 0.25:
        return "medium"
    return "low"


def to_rows(ranked: pd.DataFrame, w: Weights = Weights()) -> list[dict]:
    """Shape ranked patients for the API. Never includes DEATH_EVENT or time."""
    rows = []
    for _, r in ranked.iterrows():
        rows.append({
            "rank": int(r["rank"]) if "rank" in r else None,
            "patient_id": int(r["patient_id"]),
            "age": int(r["age"]),
            "ef": int(r["ejection_fraction"]),
            "creatinine": round(float(r["serum_creatinine"]), 2),
            "score": _num(r["score"]),
            "band": risk_band(r["score"], w),
            "why": reasons(r, w),
        })
    return rows
