from datetime import datetime, timezone

from jose import jwt

from app import auth


def test_password_hash_verifies_only_original_password():
    hashed_password = auth.get_password_hash("brewing-password")

    assert hashed_password != "brewing-password"
    assert auth.verify_password("brewing-password", hashed_password)
    assert not auth.verify_password("different-password", hashed_password)


def test_access_token_contains_subject_and_expiration():
    token = auth.create_access_token({"sub": "brewer@example.com"})
    payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])

    assert payload["sub"] == "brewer@example.com"
    assert datetime.fromtimestamp(payload["exp"], timezone.utc) > datetime.now(timezone.utc)
