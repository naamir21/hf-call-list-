import pytest
from fastapi.testclient import TestClient
from app import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def login(c, u, p):
    r = c.post("/api/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}

@pytest.fixture(scope="module")
def nurse(client): return login(client, "nurse", "nurse-demo-1")

@pytest.fixture(scope="module")
def manager(client): return login(client, "manager", "manager-demo-1")

def test_page_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "call list" in r.text.lower()
    assert "Not a diagnosis".lower() in r.text.lower()

def test_requires_login(client):
    r = client.get("/api/calllist")
    assert r.status_code == 401 and r.json()["error"] == "unauthorized"
    assert client.get("/api/calllist", headers={"Authorization": "Bearer junk"}).status_code == 401

def test_bad_login(client):
    r = client.post("/api/login", json={"username": "nurse", "password": "nope"})
    assert r.status_code == 401 and set(r.json()) == {"error", "detail"}

def test_calllist(client, nurse):
    r = client.get("/api/calllist?hi=2", headers=nurse).json()
    assert len(r["patients"]) == 25
    p = r["patients"][0]
    assert {"rank", "patient_id", "age", "ef", "creatinine", "score", "band", "why"} == set(p)
    assert [x["rank"] for x in r["patients"]] == list(range(1, 26))

def test_hi_changes_list(client, nurse):
    a = {p["patient_id"] for p in client.get("/api/calllist?hi=2", headers=nurse).json()["patients"]}
    b = {p["patient_id"] for p in client.get("/api/calllist?hi=3", headers=nurse).json()["patients"]}
    assert a != b

def test_oldest_strategy(client, nurse):
    ages = [p["age"] for p in client.get("/api/calllist?strategy=oldest", headers=nurse).json()["patients"]]
    assert ages == sorted(ages, reverse=True)

@pytest.mark.parametrize("q", ["hi=-1", "hi=abc", "hi=1000", "strategy=random", "n=0"])
def test_bad_params(client, nurse, q):
    r = client.get("/api/calllist?" + q, headers=nurse)
    assert r.status_code == 422 and r.json()["error"] == "invalid_input"

def test_compare(client, nurse):
    r = client.get("/api/compare?hi=2&hi_revise=3", headers=nurse).json()
    assert r["deaths_v1"] > r["deaths_oldest_first"]
    assert {"overlap_baseline_v1", "overlap_v1_revised", "rose", "fell"} <= set(r)

def test_nurse_cannot_set_weights_or_read_audit(client, nurse):
    assert client.put("/api/weights", json={"hi": 3}, headers=nurse).status_code == 403
    assert client.get("/api/audit", headers=nurse).status_code == 403

def test_manager_sets_weights(client, manager, nurse):
    r = client.put("/api/weights", json={"hi": 3}, headers=manager)
    assert r.status_code == 200 and r.json()["hi"] == 3
    assert client.get("/api/weights", headers=nurse).json()["hi"] == 3
    assert client.get("/api/calllist", headers=nurse).json()["weights"]["hi"] == 3
    assert client.put("/api/weights", json={"hi": -2}, headers=manager).status_code == 422
    client.put("/api/weights", json={"hi": 2}, headers=manager)

def test_audit_records_views(client, manager, nurse):
    client.get("/api/calllist?hi=2", headers=nurse)
    log = client.get("/api/audit", headers=manager).json()
    actions = {e["action"] for e in log}
    assert {"view_calllist", "login", "login_failed", "set_weights", "denied"} <= actions

def test_export_csv(client, nurse):
    r = client.get("/api/export.csv", headers=nurse)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert len(lines) == 26 and "DEATH" not in r.text

def test_security_headers(client):
    r = client.get("/")
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'self'" in r.headers["Content-Security-Policy"]
