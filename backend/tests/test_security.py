import time
import uuid

import jwt
import pytest

from app.core.security import AuthError, TokenVerifier

SECRET = "test-secret-with-enough-length-0123456789"
ISSUER = "https://example.supabase.co/auth/v1"


def _token(**overrides):
    now = int(time.time())
    claims = {"sub": str(uuid.uuid4()), "aud": "authenticated", "role": "authenticated",
              "email": "a@b.test", "iat": now, "exp": now + 3600, "iss": ISSUER}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, SECRET, algorithm="HS256"), claims


@pytest.fixture
def verifier():
    return TokenVerifier(audience="authenticated", hs256_secret=SECRET, issuer=ISSUER)


def test_valid_token(verifier):
    tok, claims = _token()
    user = verifier.verify(tok)
    assert str(user.id) == claims["sub"]
    assert user.email == "a@b.test"


def test_expired_token_rejected(verifier):
    tok, _ = _token(exp=int(time.time()) - 3600)
    with pytest.raises(AuthError, match="expirée"):
        verifier.verify(tok)


def test_wrong_secret_rejected(verifier):
    tok = jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated", "role": "authenticated",
                      "exp": int(time.time()) + 60, "iss": ISSUER}, "another-secret-of-sufficient-length!", "HS256")
    with pytest.raises(AuthError):
        verifier.verify(tok)


def test_wrong_audience_rejected(verifier):
    tok, _ = _token(aud="anon")
    with pytest.raises(AuthError):
        verifier.verify(tok)


def test_wrong_issuer_rejected(verifier):
    tok, _ = _token(iss="https://evil.example/auth/v1")
    with pytest.raises(AuthError):
        verifier.verify(tok)


def test_anon_role_rejected(verifier):
    tok, _ = _token(role="anon")
    with pytest.raises(AuthError, match="Rôle"):
        verifier.verify(tok)


def test_service_role_token_rejected(verifier):
    tok, _ = _token(role="service_role")
    with pytest.raises(AuthError):
        verifier.verify(tok)


def test_alg_none_rejected(verifier):
    tok = jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated", "role": "authenticated",
                      "exp": int(time.time()) + 60}, key=None, algorithm="none")
    with pytest.raises(AuthError, match="Algorithme"):
        verifier.verify(tok)


def test_missing_sub_rejected(verifier):
    tok, _ = _token(sub=None)
    with pytest.raises(AuthError):
        verifier.verify(tok)


def test_non_uuid_sub_rejected(verifier):
    tok, _ = _token(sub="not-a-uuid")
    with pytest.raises(AuthError):
        verifier.verify(tok)


def test_garbage_rejected(verifier):
    for bad in ["", "abc", "a.b.c"]:
        with pytest.raises(AuthError):
            verifier.verify(bad)


def test_requires_key_material():
    with pytest.raises(ValueError):
        TokenVerifier(audience="authenticated")
