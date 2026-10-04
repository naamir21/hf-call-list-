"""FastAPI app: REST API + audit log + static dashboard.

Run:  uvicorn app:app --reload     then open http://127.0.0.1:8000
"""
import io
import json
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import auth
import db
from evaluation import compare as run_compare
from scoring import Weights, WeightError, oldest_first, rank, score_patients, to_rows, TOP_N

STATIC = db.ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not db.DB.exists():
        db.build()
    else:
        with db.connect() as con:
            con.executescript(db.SCHEMA)   # make sure newer tables exist
    created = auth.seed_demo_users()
    if created:
        print("Demo users created:", ", ".join(created), "(see README for passwords)")
    yield


app = FastAPI(title="Heart-Failure Call List", version="1.0", lifespan=lifespan)


# ---------- errors: always JSON {error, detail} ----------
@app.exception_handler(StarletteHTTPException)
async def http_err(_: Request, exc: StarletteHTTPException):
    names = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
             405: "method_not_allowed", 409: "conflict", 422: "invalid_input"}
    return JSONResponse({"error": names.get(exc.status_code, "error"), "detail": exc.detail},
                        status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_err(_: Request, exc: RequestValidationError):
    detail = "; ".join(f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
    return JSONResponse({"error": "invalid_input", "detail": detail}, status_code=422)


@app.exception_handler(Exception)
async def server_err(_: Request, exc: Exception):
    return JSONResponse({"error": "server_error", "detail": "Something went wrong on the server."},
                        status_code=500)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    else:
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
    return resp


# ---------- auth + audit helpers ----------
def audit(user_id: Optional[int], action: str, detail: dict | str | None = None):
    if isinstance(detail, dict):
        detail = json.dumps(detail, separators=(",", ":"))
    with db.connect() as con:
        con.execute("INSERT INTO audit_log (user_id, action, detail) VALUES (?,?,?)",
                    (user_id, action, detail))


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Log in first. Send 'Authorization: Bearer <token>'.")
    payload = auth.read_token(authorization.split(" ", 1)[1].strip())
    if payload is None:
        raise HTTPException(401, "Session expired or invalid. Log in again.")
    return {"user_id": payload["uid"], "username": payload["u"], "role": payload["r"]}


def manager_only(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "manager":
        audit(user["user_id"], "denied", "manager-only action")
        raise HTTPException(403, "Only a clinic manager can do this.")
    return user


def active_weights() -> tuple[int, Weights]:
    with db.connect() as con:
        row = con.execute("SELECT * FROM weight_config WHERE active=1 "
                          "ORDER BY config_id DESC LIMIT 1").fetchone()
    if row is None:
        return 0, Weights()
    return row["config_id"], Weights(hi=row["hi"], extra=row["extra"],
                                     age_cut=int(row["age_cut"]), age_pts=row["age_pts"])


def weights_from(hi: Optional[float]) -> Weights:
    _, w = active_weights()
    if hi is None:
        return w
    try:
        return Weights(hi=hi, extra=w.extra, age_cut=w.age_cut, age_pts=w.age_pts)
    except WeightError as e:
        raise HTTPException(422, str(e))


def patients():
    df = db.load()
    if df.empty:
        raise HTTPException(409, "No patients loaded. Run `python db.py`.")
    return df


HiParam = Query(None, ge=0, le=100, description="Weak-heart/kidney weight. Default: active config.")


# ---------- routes ----------
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@app.post("/api/login")
def login(body: LoginIn):
    user = auth.authenticate(body.username, body.password)
    if user is None:
        audit(None, "login_failed", {"username": body.username[:64]})
        raise HTTPException(401, "Wrong username or password.")
    audit(user["user_id"], "login")
    return {"token": auth.make_token(user["user_id"], user["username"], user["role"]),
            "username": user["username"], "role": user["role"]}


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


@app.get("/api/status")
def status(user: dict = Depends(current_user)):
    cid, w = active_weights()
    return {"cleaning": db.cleaning_report(), "active_weights": w.as_dict(), "config_id": cid}


@app.get("/api/calllist")
def calllist(hi: Optional[float] = HiParam,
             strategy: str = Query("risk", pattern="^(risk|oldest)$"),
             n: int = Query(TOP_N, ge=1, le=500),
             user: dict = Depends(current_user)):
    w = weights_from(hi)
    df = patients()
    scored = score_patients(df, w)
    if strategy == "oldest":
        ranked = oldest_first(scored, n)
        ranked["rank"] = ranked.index + 1
    else:
        ranked = rank(scored).head(n)
    audit(user["user_id"], "view_calllist", {"hi": w.hi, "strategy": strategy, "n": n})
    return {"weights": w.as_dict(), "strategy": strategy, "n": min(n, len(df)),
            "patients": to_rows(ranked, w)}


@app.get("/api/compare")
def compare(hi: Optional[float] = HiParam,
            hi_revise: float = Query(3, ge=0, le=100),
            user: dict = Depends(current_user)):
    w1 = weights_from(hi)
    w2 = weights_from(hi_revise)
    result = run_compare(patients(), w1, w2)
    audit(user["user_id"], "view_compare", {"hi": w1.hi, "hi_revise": w2.hi})
    return result


class WeightsIn(BaseModel):
    hi: float = Field(ge=0, le=100)
    extra: float = Field(1, ge=0, le=100)
    age_cut: int = Field(70, ge=0, le=120)
    age_pts: float = Field(1, ge=0, le=100)


@app.get("/api/weights")
def get_weights(user: dict = Depends(current_user)):
    cid, w = active_weights()
    return {"config_id": cid, **w.as_dict()}


@app.put("/api/weights")
def put_weights(body: WeightsIn, user: dict = Depends(manager_only)):
    try:
        w = Weights(hi=body.hi, extra=body.extra, age_cut=body.age_cut, age_pts=body.age_pts)
    except WeightError as e:
        raise HTTPException(422, str(e))
    ranked = rank(score_patients(patients(), w))
    with db.connect() as con:
        con.execute("UPDATE weight_config SET active=0")
        cid = con.execute("INSERT INTO weight_config (hi, extra, age_cut, age_pts, active, created_by) "
                          "VALUES (?,?,?,?,1,?)",
                          (w.hi, w.extra, w.age_cut, w.age_pts, user["username"])).lastrowid
        con.executemany("INSERT INTO score_result (patient_id, config_id, score, rank, reasons) "
                        "VALUES (?,?,?,?,?)",
                        [(int(r.patient_id), cid, float(r.score), int(r.rank),
                          json.dumps(row["why"]))
                         for r, row in zip(ranked.itertuples(), to_rows(ranked, w))])
    audit(user["user_id"], "set_weights", {"config_id": cid, **w.as_dict()})
    return {"config_id": cid, **w.as_dict()}


@app.get("/api/audit")
def get_audit(limit: int = Query(100, ge=1, le=1000), user: dict = Depends(manager_only)):
    with db.connect() as con:
        rows = con.execute("SELECT a.log_id, u.username, a.action, a.detail, a.at FROM audit_log a "
                           "LEFT JOIN user u ON u.user_id = a.user_id "
                           "ORDER BY a.log_id DESC LIMIT ?", (limit,)).fetchall()
    audit(user["user_id"], "view_audit")
    return [dict(r) for r in rows]


@app.get("/api/export.csv")
def export_csv(hi: Optional[float] = HiParam, user: dict = Depends(current_user)):
    w = weights_from(hi)
    rows = to_rows(rank(score_patients(patients(), w)).head(TOP_N), w)
    buf = io.StringIO()
    buf.write("rank,patient,age,ejection_fraction,creatinine,score,why\n")
    for r in rows:
        why = "; ".join(r["why"])
        buf.write(f'{r["rank"]},P-{r["patient_id"]},{r["age"]},{r["ef"]},{r["creatinine"]},'
                  f'{r["score"]},"{why}"\n')
    audit(user["user_id"], "export_csv", {"hi": w.hi})
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="call_list.csv"'})


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")  # keep LAST
