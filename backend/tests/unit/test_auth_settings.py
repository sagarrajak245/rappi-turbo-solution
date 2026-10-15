"""Dev-only auth defaults (JWT secret, seed passwords) are refused outside local and test."""

import pytest

from app.core.config import AuthSettings, Settings


@pytest.mark.parametrize("env", ["local", "test"])
def test_dev_defaults_allowed_locally(env: str) -> None:
    assert Settings(app_env=env).auth.jwt_secret


@pytest.mark.parametrize(
    "auth",
    [
        AuthSettings(),
        AuthSettings(seed_buyer_password="b" * 16, seed_admin_password="a" * 16),
        AuthSettings(jwt_secret="s" * 40, seed_buyer_password="b" * 16),
    ],
)
def test_dev_defaults_refused_elsewhere(auth: AuthSettings) -> None:
    with pytest.raises(ValueError, match="AUTH__"):
        Settings(app_env="production", auth=auth)


def test_real_values_accepted_elsewhere() -> None:
    auth = AuthSettings(
        jwt_secret="s" * 40, seed_buyer_password="b" * 16, seed_admin_password="a" * 16
    )
    assert Settings(app_env="production", auth=auth).auth.jwt_secret == "s" * 40


def test_refusal_never_echoes_the_secret_values() -> None:
    # The error lands in hosting logs; it must name the keys, never their values.
    secret = "leaky-but-not-dev-secret-value-0123456789"
    with pytest.raises(ValueError) as err:
        Settings(app_env="production", auth=AuthSettings(jwt_secret=secret))
    text = str(err.value)
    assert "AUTH__SEED_BUYER_PASSWORD" in text
    assert secret not in text
    assert AuthSettings().seed_admin_password not in text
