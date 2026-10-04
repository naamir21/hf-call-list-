"""Ingestion, cleaning and the SQLite database.

Run `python db.py` once to (re)build patients.db from the CSV.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
CSV = ROOT / "data" / "heart_failure_clinical_records.csv"
DB = Path(os.environ.get("HF_DB", ROOT / "patients.db"))

COLUMNS = ["age", "anaemia", "creatinine_phosphokinase", "diabetes",
           "ejection_fraction", "high_blood_pressure", "platelets",
           "serum_creatinine", "serum_sodium", "sex", "smoking", "time",
           "DEATH_EVENT"]
FLAGS = ["anaemia", "diabetes", "high_blood_pressure", "sex", "smoking", "DEATH_EVENT"]
# Plausible clinical ranges; anything outside is flagged and dropped.
RANGES = {
    "age": (0, 120),
    "ejection_fraction": (5, 100),
    "serum_creatinine": (0.1, 20),
    "serum_sodium": (90, 180),
    "creatinine_phosphokinase": (0, 100000),
    "platelets": (0, 2_000_000),
    "time": (0, 10000),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS patient (
  patient_id INTEGER PRIMARY KEY,
  age REAL NOT NULL,
  anaemia INTEGER NOT NULL CHECK (anaemia IN (0,1)),
  creatinine_phosphokinase INTEGER NOT NULL,
  diabetes INTEGER NOT NULL CHECK (diabetes IN (0,1)),
  ejection_fraction INTEGER NOT NULL CHECK (ejection_fraction BETWEEN 5 AND 100),
  high_blood_pressure INTEGER NOT NULL CHECK (high_blood_pressure IN (0,1)),
  platelets REAL NOT NULL,
  serum_creatinine REAL NOT NULL,
  serum_sodium INTEGER NOT NULL,
  sex INTEGER NOT NULL CHECK (sex IN (0,1)),
  smoking INTEGER NOT NULL CHECK (smoking IN (0,1)),
  time INTEGER NOT NULL,
  DEATH_EVENT INTEGER NOT NULL CHECK (DEATH_EVENT IN (0,1))
);
CREATE TABLE IF NOT EXISTS weight_config (
  config_id INTEGER PRIMARY KEY AUTOINCREMENT,
  hi REAL NOT NULL CHECK (hi >= 0),
  extra REAL NOT NULL CHECK (extra >= 0),
  age_cut INTEGER NOT NULL CHECK (age_cut >= 0),
  age_pts REAL NOT NULL CHECK (age_pts >= 0),
  active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0,1)),
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS score_result (
  patient_id INTEGER NOT NULL REFERENCES patient(patient_id),
  config_id INTEGER NOT NULL REFERENCES weight_config(config_id),
  score REAL NOT NULL,
  rank INTEGER NOT NULL CHECK (rank >= 1),
  reasons TEXT NOT NULL,
  PRIMARY KEY (patient_id, config_id)
);
CREATE TABLE IF NOT EXISTS user (
  user_id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('nurse','manager'))
);
CREATE TABLE IF NOT EXISTS audit_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER REFERENCES user(user_id),
  action TEXT NOT NULL,
  detail TEXT,
  at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- audit_log is append-only
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


class DataError(ValueError):
    pass


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Validate and clean. Returns (clean_df, report). Raises DataError on missing columns."""
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise DataError(f"CSV is missing required columns: {missing}")
    df = df[COLUMNS].copy()
    report = {"rows_in": int(len(df)), "dropped_missing": 0,
              "dropped_bad_type": 0, "dropped_out_of_range": 0, "flagged": []}

    before = len(df)
    df = df.dropna()
    report["dropped_missing"] = before - len(df)

    before = len(df)
    for c in COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna()
    report["dropped_bad_type"] = before - len(df)

    bad = pd.Series(False, index=df.index)
    for c in FLAGS:
        m = ~df[c].isin([0, 1])
        if m.any(): report["flagged"].append(f"{c}: {int(m.sum())} not 0/1")
        bad |= m
    for c, (lo, hi) in RANGES.items():
        m = (df[c] < lo) | (df[c] > hi)
        if m.any(): report["flagged"].append(f"{c}: {int(m.sum())} outside {lo}-{hi}")
        bad |= m
    report["dropped_out_of_range"] = int(bad.sum())
    df = df[~bad].reset_index(drop=True)

    for c in FLAGS + ["ejection_fraction", "serum_sodium", "creatinine_phosphokinase", "time"]:
        df[c] = df[c].astype(int)
    report["rows_kept"] = int(len(df))
    report["rows_dropped"] = report["rows_in"] - report["rows_kept"]
    return df, report


@contextmanager
def connect(path: Path | None = None):
    con = sqlite3.connect(path or DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def build(csv: Path = CSV, path: Path | None = None, verbose: bool = True) -> dict:
    """(Re)build the patient table. Keeps users and the audit log."""
    if not Path(csv).exists():
        raise DataError(f"CSV not found: {csv}. Put it in data/.")
    df, report = clean(pd.read_csv(csv))
    df.insert(0, "patient_id", df.index + 1)
    with connect(path) as con:
        con.executescript(SCHEMA)
        con.execute("DELETE FROM score_result")
        con.execute("DELETE FROM patient")
        df.to_sql("patient", con, if_exists="append", index=False)
        if con.execute("SELECT COUNT(*) FROM weight_config").fetchone()[0] == 0:
            con.execute("INSERT INTO weight_config (hi, extra, age_cut, age_pts, active, created_by) "
                        "VALUES (2, 1, 70, 1, 1, 'system')")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('cleaning_report', ?)", (json.dumps(report),))
    if verbose:
        print(f"Dropped {report['rows_dropped']} rows. Stored {report['rows_kept']} patients.")
        for f in report["flagged"]:
            print("  flagged:", f)
    return report


def load(path: Path | None = None) -> pd.DataFrame:
    with connect(path) as con:
        return pd.read_sql("SELECT * FROM patient ORDER BY patient_id", con)


def cleaning_report(path: Path | None = None) -> dict:
    with connect(path) as con:
        row = con.execute("SELECT value FROM meta WHERE key='cleaning_report'").fetchone()
    return json.loads(row["value"]) if row else {}


if __name__ == "__main__":
    build()
