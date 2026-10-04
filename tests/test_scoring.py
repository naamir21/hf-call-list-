import pandas as pd
import pytest
from scoring import Weights, WeightError, score_patients, rank, top_n, oldest_first, reasons, to_rows, risk_band

def P(**kw):
    base = dict(patient_id=1, age=50, ejection_fraction=60, serum_creatinine=1.0,
                anaemia=0, diabetes=0, high_blood_pressure=0, DEATH_EVENT=0, time=100)
    base.update(kw); return base

def test_one_sentence_score():
    df = pd.DataFrame([P(ejection_fraction=20, serum_creatinine=2.7, anaemia=1, diabetes=1, high_blood_pressure=1, age=72)])
    assert score_patients(df, Weights(hi=2))["score"].iloc[0] == 2 + 2 + 3 + 1
    assert score_patients(df, Weights(hi=3))["score"].iloc[0] == 3 + 3 + 3 + 1

def test_cut_points_are_strict():
    df = pd.DataFrame([P(ejection_fraction=35, serum_creatinine=1.5, age=69)])
    assert score_patients(df)["score"].iloc[0] == 0
    df = pd.DataFrame([P(ejection_fraction=34, serum_creatinine=1.51, age=70)])
    assert score_patients(df)["score"].iloc[0] == 5

def test_young_sick_beats_old_healthy():
    df = pd.DataFrame([P(patient_id=1, age=80), P(patient_id=2, age=55, ejection_fraction=20, serum_creatinine=2.1)])
    assert top_n(score_patients(df), 1)["patient_id"].iloc[0] == 2
    assert oldest_first(df, 1)["patient_id"].iloc[0] == 1

def test_tie_breaks_lower_ef_then_higher_creatinine():
    df = pd.DataFrame([P(patient_id=1, ejection_fraction=30), P(patient_id=2, ejection_fraction=20),
                       P(patient_id=3, ejection_fraction=20, serum_creatinine=1.4)])
    assert list(rank(score_patients(df))["patient_id"]) == [3, 2, 1]

def test_reasons_and_rows_hide_outcome():
    r = P(ejection_fraction=20, anaemia=1, age=75)
    assert reasons(r) == ["Low ejection fraction", "Anaemia", "Age 70+"]
    rows = to_rows(rank(score_patients(pd.DataFrame([r]))))
    assert "DEATH_EVENT" not in rows[0] and "time" not in rows[0]
    assert rows[0]["score"] == 4 and isinstance(rows[0]["score"], int)

def test_score_ignores_outcome_columns():
    a = pd.DataFrame([P(DEATH_EVENT=0, time=5)]); b = pd.DataFrame([P(DEATH_EVENT=1, time=250)])
    assert score_patients(a)["score"].iloc[0] == score_patients(b)["score"].iloc[0]

@pytest.mark.parametrize("bad", [dict(hi=-1), dict(hi=float("nan")), dict(extra=-0.5),
                                 dict(age_cut=-1), dict(age_cut=70.5), dict(hi=True), dict(hi="2")])
def test_bad_weights_rejected(bad):
    with pytest.raises(WeightError):
        Weights(**bad)

def test_missing_column_errors():
    with pytest.raises(KeyError):
        score_patients(pd.DataFrame([{"age": 50}]))

def test_risk_band():
    assert risk_band(9) == "high" and risk_band(3) == "medium" and risk_band(1) == "low"
    assert risk_band(0, Weights(hi=0, extra=0, age_pts=0)) == "low"
