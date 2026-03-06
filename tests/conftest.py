import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def app_factory(tmp_path, monkeypatch):
    def _create(**env_overrides):
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "profiles": data_dir / "credential_profiles.json",
            "playlists": data_dir / "saved_playlists.json",
            "auth": data_dir / "auth_users.json",
            "throttle": data_dir / "auth_login_throttle.json",
            "secret": data_dir / "flask_secret_key",
            "cipher": data_dir / "credential_cipher_key",
        }

        env = {
            "CREDENTIAL_PROFILE_STORE": str(paths["profiles"]),
            "PLAYLIST_STORE_PATH": str(paths["playlists"]),
            "AUTH_STORE_PATH": str(paths["auth"]),
            "AUTH_THROTTLE_STORE_PATH": str(paths["throttle"]),
            "FLASK_SECRET_FILE": str(paths["secret"]),
            "CREDENTIAL_CIPHER_FILE": str(paths["cipher"]),
            "AUTH_MAX_LOGIN_ATTEMPTS": "5",
            "AUTH_ATTEMPT_WINDOW_SECONDS": "300",
            "AUTH_LOCKOUT_SECONDS": "300",
        }
        env.update({k: str(v) for k, v in env_overrides.items()})

        for key, value in env.items():
            monkeypatch.setenv(key, value)

        import app.routes.api as api_module
        import app.routes.proxy as proxy_module
        import app.routes.static as static_module
        import app as app_module

        importlib.reload(api_module)
        importlib.reload(proxy_module)
        importlib.reload(static_module)
        importlib.reload(app_module)

        app = app_module.create_app()
        app.config.update(TESTING=True)
        return {
            "app": app,
            "client": app.test_client(),
            "api": api_module,
            "paths": {
                "CREDENTIAL_PROFILE_STORE": Path(env["CREDENTIAL_PROFILE_STORE"]),
                "PLAYLIST_STORE_PATH": Path(env["PLAYLIST_STORE_PATH"]),
                "AUTH_STORE_PATH": Path(env["AUTH_STORE_PATH"]),
                "AUTH_THROTTLE_STORE_PATH": Path(env["AUTH_THROTTLE_STORE_PATH"]),
                "FLASK_SECRET_FILE": Path(env["FLASK_SECRET_FILE"]),
                "CREDENTIAL_CIPHER_FILE": Path(env["CREDENTIAL_CIPHER_FILE"]),
            },
        }

    return _create


@pytest.fixture
def app_ctx(app_factory):
    return app_factory()


@pytest.fixture
def admin_ctx(app_factory):
    ctx = app_factory()
    response = ctx["client"].post(
        "/auth/setup",
        json={"username": "admin", "password": "password123"},
    )
    assert response.status_code == 200
    return ctx
