import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp()
os.environ["HF_DB"] = str(Path(_tmp) / "test.db")
os.environ["HF_SECRET"] = "test-secret"

import pytest
import db

@pytest.fixture(scope="session", autouse=True)
def built():
    db.build(verbose=False)
    yield

@pytest.fixture
def df():
    return db.load()
