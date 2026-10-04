import sqlite3
import pandas as pd
import pytest
import db

def test_real_data_loads(df):
    assert len(df) == 299 and df["patient_id"].is_unique
    assert db.cleaning_report()["rows_dropped"] == 0

def test_clean_drops_missing_and_out_of_range():
    raw = pd.read_csv(db.CSV).head(5).astype(object)
    raw.loc[0, "age"] = None
    raw.loc[1, "ejection_fraction"] = 150
    raw.loc[2, "anaemia"] = 2
    raw.loc[3, "serum_creatinine"] = "abc"
    out, rep = db.clean(raw)
    assert len(out) == 1 and rep["rows_dropped"] == 4
    assert rep["dropped_missing"] == 1 and rep["dropped_bad_type"] == 1 and rep["dropped_out_of_range"] == 2

def test_missing_columns_raise():
    with pytest.raises(db.DataError):
        db.clean(pd.DataFrame({"age": [50]}))

def test_missing_csv_raises(tmp_path):
    with pytest.raises(db.DataError):
        db.build(tmp_path / "nope.csv", tmp_path / "x.db", verbose=False)

def test_constraints_enforced():
    with db.connect() as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO patient VALUES (9999,50,2,1,0,40,0,1,1,140,0,0,10,0)")

def test_audit_append_only():
    with db.connect() as con:
        con.execute("INSERT INTO audit_log (action) VALUES ('t')")
    with db.connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("DELETE FROM audit_log")

def test_rebuild_is_idempotent(df):
    db.build(verbose=False); db.build(verbose=False)
    assert len(db.load()) == 299
