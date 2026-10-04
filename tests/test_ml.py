import ml_check

def test_ml_check(df):
    r = ml_check.run(df)
    assert "time" not in ml_check.FEATURES
    assert r["top_two_are_ef_and_creatinine"]
    assert 0.6 < r["auc_cv_mean"] < 0.95
    assert r["auc_points_hi2"] > r["auc_age_only"]
