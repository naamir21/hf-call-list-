"""Machine-learning check of the hand-set point weights. Not used by the app.

Logistic regression on the 6 score inputs (never `time`: follow-up length is
only known after the outcome, so it would leak the answer).
Run: python ml_check.py
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from db import load
from scoring import Weights, TOP_N, oldest_first, rank, score_patients

FEATURES = ["age", "ejection_fraction", "serum_creatinine",
            "anaemia", "diabetes", "high_blood_pressure"]
# binary flags matching the point score, for the "round into points" check
FLAG_FEATURES = ["low_ef", "high_creat", "anaemia", "diabetes", "high_blood_pressure", "age_70"]
SEED = 42


def _flags(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "low_ef": (df["ejection_fraction"] < 35).astype(int),
        "high_creat": (df["serum_creatinine"] > 1.5).astype(int),
        "anaemia": df["anaemia"], "diabetes": df["diabetes"],
        "high_blood_pressure": df["high_blood_pressure"],
        "age_70": (df["age"] >= 70).astype(int),
    })


def _model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))


def run(df: pd.DataFrame | None = None) -> dict:
    df = load() if df is None else df
    assert "time" not in FEATURES and "DEATH_EVENT" not in FEATURES
    y = df["DEATH_EVENT"]
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)

    # 1) raw features: which factors matter most?
    X = df[FEATURES]
    auc_raw = cross_val_score(_model(), X, y, cv=cv, scoring="roc_auc")
    m = _model().fit(X, y)
    coefs = pd.Series(m.named_steps["logisticregression"].coef_[0], index=FEATURES)
    coefs = coefs.reindex(coefs.abs().sort_values(ascending=False).index)

    # 2) binary flags (same inputs as the points): learned weights rounded into points
    F = _flags(df)
    mf = LogisticRegression(max_iter=1000).fit(F, y)
    flag_coefs = pd.Series(mf.coef_[0], index=FLAG_FEATURES)
    smallest = flag_coefs[flag_coefs > 0].min() if (flag_coefs > 0).any() else 1.0
    learned_points = (flag_coefs / smallest).round().clip(lower=0).astype(int)

    # 3) ranking quality: points vs oldest-first vs out-of-fold ML probability
    pts1 = score_patients(df, Weights(hi=2))["score"]
    pts2 = score_patients(df, Weights(hi=3))["score"]
    oof = cross_val_predict(_model(), X, y, cv=cv, method="predict_proba")[:, 1]
    ml_top = df.assign(p=oof).sort_values(["p", "patient_id"], ascending=[False, True]).head(TOP_N)

    return {
        "auc_cv_mean": float(np.round(auc_raw.mean(), 3)),
        "auc_cv_folds": [float(round(a, 3)) for a in auc_raw],
        "coefficients": {k: float(round(v, 3)) for k, v in coefs.items()},
        "flag_coefficients": {k: float(round(v, 3)) for k, v in flag_coefs.items()},
        "learned_points": {k: int(v) for k, v in learned_points.items()},
        "auc_points_hi2": float(round(roc_auc_score(y, pts1), 3)),
        "auc_points_hi3": float(round(roc_auc_score(y, pts2), 3)),
        "auc_age_only": float(round(roc_auc_score(y, df["age"]), 3)),
        "deaths_top25": {
            "oldest_first": int(oldest_first(df)["DEATH_EVENT"].sum()),
            "points_hi2": int(rank(score_patients(df, Weights(hi=2))).head(TOP_N)["DEATH_EVENT"].sum()),
            "points_hi3": int(rank(score_patients(df, Weights(hi=3))).head(TOP_N)["DEATH_EVENT"].sum()),
            "ml_out_of_fold": int(ml_top["DEATH_EVENT"].sum()),
        },
        "top_two_are_ef_and_creatinine":
            set(list(coefs.index[:2])) == {"ejection_fraction", "serum_creatinine"},
    }


if __name__ == "__main__":
    r = run()
    print("AUC, 5-fold CV (0.5 = coin flip, 1.0 = perfect):", r["auc_cv_mean"], r["auc_cv_folds"])
    print("\nStandardised coefficients (bigger |value| = stronger; negative EF = low EF is risky):")
    for k, v in r["coefficients"].items():
        print(f"  {k:22s} {v:+.3f}")
    print("\nEF and creatinine are the top two:", r["top_two_are_ef_and_creatinine"])
    print("\nFlag model, learned weights rounded to points:", r["learned_points"])
    print("\nWhole-list AUC  points hi=2:", r["auc_points_hi2"], " hi=3:", r["auc_points_hi3"],
          " age only:", r["auc_age_only"])
    print("Deaths in top 25:", r["deaths_top25"])
