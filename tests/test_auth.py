import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from gitpulse.github.auth import GitHubAppAuth


@pytest.fixture(scope="module")
def keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private, public


def test_app_jwt_claims(keypair):
    private, public = keypair
    auth = GitHubAppAuth("123456", private, session=None)  # type: ignore[arg-type]

    token = auth.app_jwt()
    claims = jwt.decode(token, public, algorithms=["RS256"])

    assert claims["iss"] == "123456"
    assert claims["iat"] <= time.time()
    # GitHub rejects anything over 10 minutes
    assert claims["exp"] - claims["iat"] <= 600


def test_app_jwt_is_cached(keypair):
    private, _ = keypair
    auth = GitHubAppAuth("1", private, session=None)  # type: ignore[arg-type]
    assert auth.app_jwt() == auth.app_jwt()
