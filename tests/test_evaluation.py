from evaluation import compare
from scoring import Weights

def test_beats_baseline_and_shape(df):
    r = compare(df, Weights(hi=2), Weights(hi=3))
    assert r["n"] == 25 and r["total_deaths"] == 96
    assert r["deaths_v1"] > r["deaths_oldest_first"]
    assert len(r["rose"]) == len(r["fell"]) == 25 - r["overlap_v1_revised"]

def test_risers_have_pump_and_kidney(df):
    r = compare(df, Weights(hi=2), Weights(hi=3))
    assert all(m["pump_and_kidney"] for m in r["rose"])
    assert all(m["rank_after"] <= 25 < m["rank_before"] for m in r["rose"])

def test_same_weights_no_movers(df):
    r = compare(df, Weights(hi=2), Weights(hi=2))
    assert r["overlap_v1_revised"] == 25 and r["rose"] == [] == r["fell"]

def test_fewer_than_25(df):
    r = compare(df.head(10), Weights(), Weights(hi=3))
    assert r["n"] == 10 and "Only 10" in r["note"]
