import auth

def test_hash_roundtrip():
    h = auth.hash_password("secret-pass")
    assert auth.verify_password("secret-pass", h) and not auth.verify_password("wrong", h)
    assert "secret-pass" not in h
    assert not auth.verify_password("x", "garbage")

def test_token_roundtrip_tamper_expiry():
    t = auth.make_token(1, "nurse", "nurse", now=1000)
    assert auth.read_token(t, now=1001)["r"] == "nurse"
    assert auth.read_token(t, now=1000 + auth.TOKEN_TTL + 1) is None
    body, sig = t.split(".")
    forged = auth._b64(b'{"uid":1,"u":"nurse","r":"manager","exp":9999999999}')
    assert auth.read_token(f"{forged}.{sig}") is None
    assert auth.read_token("not-a-token") is None
