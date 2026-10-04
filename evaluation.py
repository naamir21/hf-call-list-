"""Compare ranking strategies. DEATH_EVENT is used here only as the answer key."""
import pandas as pd

from scoring import (Weights, TOP_N, score_patients, rank, oldest_first,
                     reasons, EF_CUT, CREAT_CUT)


def _ids(d: pd.DataFrame) -> set[int]:
    return set(int(i) for i in d["patient_id"])


def _summary(d: pd.DataFrame) -> dict:
    return {
        "deaths": int(d["DEATH_EVENT"].sum()),
        "mean_ef": round(float(d["ejection_fraction"].mean()), 1),
        "mean_creatinine": round(float(d["serum_creatinine"].mean()), 2),
        "mean_age": round(float(d["age"].mean()), 1),
    }


def _mover(row, full_rank: dict, w: Weights) -> dict:
    both = row["ejection_fraction"] < EF_CUT and row["serum_creatinine"] > CREAT_CUT
    return {
        "patient_id": int(row["patient_id"]),
        "age": int(row["age"]),
        "ef": int(row["ejection_fraction"]),
        "creatinine": round(float(row["serum_creatinine"]), 2),
        "rank_before": full_rank["before"].get(int(row["patient_id"])),
        "rank_after": full_rank["after"].get(int(row["patient_id"])),
        "why": reasons(row, w),
        "pump_and_kidney": bool(both),
    }


def compare(df: pd.DataFrame, w1: Weights, w2: Weights, n: int = TOP_N) -> dict:
    n_used = min(n, len(df))
    note = None if len(df) >= n else f"Only {len(df)} patients available; using all of them."

    base = oldest_first(df, n_used)
    r1 = rank(score_patients(df, w1))
    r2 = rank(score_patients(df, w2))
    v1, v2 = r1.head(n_used), r2.head(n_used)

    full_rank = {"before": dict(zip(r1["patient_id"].astype(int), r1["rank"].astype(int))),
                 "after": dict(zip(r2["patient_id"].astype(int), r2["rank"].astype(int)))}
    rose_ids = _ids(v2) - _ids(v1)
    fell_ids = _ids(v1) - _ids(v2)
    rose = [_mover(r, full_rank, w2) for _, r in r2[r2["patient_id"].isin(rose_ids)].iterrows()]
    fell = [_mover(r, full_rank, w1) for _, r in r1[r1["patient_id"].isin(fell_ids)].iterrows()]

    return {
        "n": n_used,
        "note": note,
        "patients_ranked": int(len(df)),
        "total_deaths": int(df["DEATH_EVENT"].sum()),
        "weights_v1": w1.as_dict(),
        "weights_revised": w2.as_dict(),
        "oldest_first": _summary(base),
        "v1": _summary(v1),
        "revised": _summary(v2),
        # flat fields kept for the build-guide API shape
        "deaths_oldest_first": int(base["DEATH_EVENT"].sum()),
        "deaths_v1": int(v1["DEATH_EVENT"].sum()),
        "deaths_revised": int(v2["DEATH_EVENT"].sum()),
        "overlap_baseline_v1": len(_ids(base) & _ids(v1)),
        "overlap_v1_revised": len(_ids(v1) & _ids(v2)),
        "rose": rose,
        "fell": fell,
    }
