import json


def test_auth_setup_status_login_logout_flow(app_ctx):
    client = app_ctx["client"]

    status = client.get("/auth/status")
    assert status.status_code == 200
    assert status.json["needs_setup"] is True
    assert status.json["authenticated"] is False

    setup = client.post("/auth/setup", json={"username": "admin", "password": "password123"})
    assert setup.status_code == 200
    assert setup.json["is_admin"] is True

    status = client.get("/auth/status")
    assert status.status_code == 200
    assert status.json["needs_setup"] is False
    assert status.json["authenticated"] is True
    assert status.json["username"] == "admin"

    logout = client.post("/auth/logout")
    assert logout.status_code == 200

    bad_login = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad_login.status_code == 401

    ok_login = client.post("/auth/login", json={"username": "admin", "password": "password123"})
    assert ok_login.status_code == 200
    assert ok_login.json["ok"] is True


def test_login_rate_limit_and_lockout(app_factory):
    ctx = app_factory(
        AUTH_MAX_LOGIN_ATTEMPTS=3,
        AUTH_ATTEMPT_WINDOW_SECONDS=120,
        AUTH_LOCKOUT_SECONDS=60,
    )
    client = ctx["client"]

    setup = client.post("/auth/setup", json={"username": "admin", "password": "password123"})
    assert setup.status_code == 200
    client.post("/auth/logout")

    for _ in range(3):
        failed = client.post("/auth/login", json={"username": "admin", "password": "bad-pass"})
        assert failed.status_code == 401

    locked = client.post("/auth/login", json={"username": "admin", "password": "password123"})
    assert locked.status_code == 429
    assert "retry_after" in locked.json
    assert int(locked.headers.get("Retry-After", "0")) > 0


def test_admin_delete_user_cascades_records(admin_ctx):
    client = admin_ctx["client"]
    profile_store = admin_ctx["paths"]["CREDENTIAL_PROFILE_STORE"]
    playlist_store = admin_ctx["paths"]["PLAYLIST_STORE_PATH"]

    create_user = client.post(
        "/auth/users",
        json={"username": "bob", "password": "password123", "is_admin": False},
    )
    assert create_user.status_code == 200

    save_profile = client.post(
        "/profiles",
        json={
            "name": "bob-svc",
            "url": "http://provider",
            "username": "bobu",
            "password": "bobp",
            "owner": "bob",
        },
    )
    assert save_profile.status_code == 200

    save_playlist = client.post(
        "/saved-playlists",
        json={
            "name": "bob-list",
            "url": "http://provider",
            "username": "bobu",
            "password": "bobp",
            "owner": "bob",
        },
    )
    assert save_playlist.status_code == 200

    deleted = client.post("/auth/users/delete", json={"username": "bob"})
    assert deleted.status_code == 200
    assert deleted.json["deleted_profiles"] == 1
    assert deleted.json["deleted_playlists"] == 1

    profiles = json.loads(profile_store.read_text(encoding="utf-8"))
    playlists = json.loads(playlist_store.read_text(encoding="utf-8"))
    assert all(item.get("owner") != "bob" for item in profiles)
    assert all(item.get("owner") != "bob" for item in playlists)
