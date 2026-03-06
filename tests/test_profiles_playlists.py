import io
import json
from pathlib import Path


def test_profile_credentials_encrypted_at_rest(admin_ctx):
    client = admin_ctx["client"]
    api = admin_ctx["api"]
    profile_store = admin_ctx["paths"]["CREDENTIAL_PROFILE_STORE"]

    response = client.post(
        "/profiles",
        json={
            "name": "svc-1",
            "url": "http://provider",
            "username": "u1",
            "password": "plain-secret",
        },
    )
    assert response.status_code == 200

    loaded = client.get("/profiles")
    assert loaded.status_code == 200
    assert loaded.json["profiles"][0]["password"] == "plain-secret"

    raw = json.loads(profile_store.read_text(encoding="utf-8"))
    assert raw[0]["password"] != "plain-secret"
    assert str(raw[0]["password"]).startswith(api.CREDENTIAL_CIPHER_PREFIX)


def test_playlist_credentials_encrypted_at_rest(admin_ctx):
    client = admin_ctx["client"]
    api = admin_ctx["api"]
    playlist_store = admin_ctx["paths"]["PLAYLIST_STORE_PATH"]

    response = client.post(
        "/saved-playlists",
        json={
            "name": "list-1",
            "url": "http://provider",
            "username": "u1",
            "password": "playlist-secret",
        },
    )
    assert response.status_code == 200

    raw = json.loads(playlist_store.read_text(encoding="utf-8"))
    assert raw[0]["config"]["password"] != "playlist-secret"
    assert str(raw[0]["config"]["password"]).startswith(api.CREDENTIAL_CIPHER_PREFIX)


def test_user_sees_only_owned_profiles_and_playlists(admin_ctx):
    client = admin_ctx["client"]

    create_user = client.post(
        "/auth/users",
        json={"username": "alice", "password": "password123", "is_admin": False},
    )
    assert create_user.status_code == 200

    admin_profile = client.post(
        "/profiles",
        json={"name": "admin-svc", "url": "http://admin", "username": "adminu", "password": "adminp"},
    )
    assert admin_profile.status_code == 200

    user_profile = client.post(
        "/profiles",
        json={
            "name": "alice-svc",
            "url": "http://alice",
            "username": "aliceu",
            "password": "alicep",
            "owner": "alice",
        },
    )
    assert user_profile.status_code == 200

    user_playlist = client.post(
        "/saved-playlists",
        json={
            "name": "alice-list",
            "url": "http://alice",
            "username": "aliceu",
            "password": "alicep",
            "owner": "alice",
        },
    )
    assert user_playlist.status_code == 200

    client.post("/auth/logout")
    login = client.post("/auth/login", json={"username": "alice", "password": "password123"})
    assert login.status_code == 200

    profiles = client.get("/profiles")
    assert profiles.status_code == 200
    names = [item["name"] for item in profiles.json["profiles"]]
    assert names == ["alice-svc"]

    playlists = client.get("/saved-playlists?url=http://alice&username=aliceu")
    assert playlists.status_code == 200
    assert [item["name"] for item in playlists.json["items"]] == ["alice-list"]


def test_admin_saved_playlists_filter_by_selected_owner(admin_ctx):
    client = admin_ctx["client"]

    create_user = client.post(
        "/auth/users",
        json={"username": "james", "password": "password123", "is_admin": False},
    )
    assert create_user.status_code == 200

    # Same upstream credentials, different owners.
    admin_playlist = client.post(
        "/saved-playlists",
        json={
            "name": "admin-list",
            "url": "http://provider",
            "username": "shared-user",
            "password": "shared-pass",
            "owner": "admin",
        },
    )
    assert admin_playlist.status_code == 200

    james_playlist = client.post(
        "/saved-playlists",
        json={
            "name": "james-list",
            "url": "http://provider",
            "username": "shared-user",
            "password": "shared-pass",
            "owner": "james",
        },
    )
    assert james_playlist.status_code == 200

    admin_view = client.get("/saved-playlists?url=http://provider&username=shared-user&owner=admin")
    assert admin_view.status_code == 200
    assert [item["name"] for item in admin_view.json["items"]] == ["admin-list"]

    james_view = client.get("/saved-playlists?url=http://provider&username=shared-user&owner=james")
    assert james_view.status_code == 200
    assert [item["name"] for item in james_view.json["items"]] == ["james-list"]


def test_backup_download_and_restore_roundtrip(admin_ctx):
    client = admin_ctx["client"]
    api = admin_ctx["api"]
    profile_store = admin_ctx["paths"]["CREDENTIAL_PROFILE_STORE"]
    playlist_store = admin_ctx["paths"]["PLAYLIST_STORE_PATH"]

    save_profile = client.post(
        "/profiles",
        json={
            "name": "svc-backup",
            "url": "http://provider",
            "username": "u1",
            "password": "secret1",
        },
    )
    assert save_profile.status_code == 200

    save_playlist = client.post(
        "/saved-playlists",
        json={
            "name": "list-backup",
            "url": "http://provider",
            "username": "u1",
            "password": "secret2",
        },
    )
    assert save_playlist.status_code == 200

    backup = client.get("/backup/download")
    assert backup.status_code == 200
    payload = json.loads(backup.data.decode("utf-8"))
    assert payload["profiles"][0]["password"] == "secret1"
    assert payload["saved_playlists"][0]["config"]["password"] == "secret2"

    restore = client.post(
        "/backup/restore",
        data={"file": (io.BytesIO(json.dumps(payload).encode("utf-8")), "backup.json")},
        content_type="multipart/form-data",
    )
    assert restore.status_code == 200
    assert restore.json["ok"] is True

    # Restored credentials remain usable in API responses.
    restored_profiles = client.get("/profiles")
    assert restored_profiles.status_code == 200
    assert restored_profiles.json["profiles"][0]["password"] == "secret1"

    restored_playlist = client.get(f"/saved-playlists/{payload['saved_playlists'][0]['id']}")
    assert restored_playlist.status_code == 200
    assert restored_playlist.json["config"]["password"] == "secret2"

    # Storage remains encrypted at rest after restore.
    raw_profiles = json.loads(profile_store.read_text(encoding="utf-8"))
    assert str(raw_profiles[0]["password"]).startswith(api.CREDENTIAL_CIPHER_PREFIX)
    raw_playlists = json.loads(playlist_store.read_text(encoding="utf-8"))
    assert str(raw_playlists[0]["config"]["password"]).startswith(api.CREDENTIAL_CIPHER_PREFIX)


def test_backup_restore_portable_across_different_cipher_keys(app_factory):
    source = app_factory()
    source_client = source["client"]

    source_setup = source_client.post("/auth/setup", json={"username": "admin", "password": "password123"})
    assert source_setup.status_code == 200

    save_profile = source_client.post(
        "/profiles",
        json={
            "name": "svc-source",
            "url": "http://provider",
            "username": "u1",
            "password": "source-secret",
        },
    )
    assert save_profile.status_code == 200

    save_playlist = source_client.post(
        "/saved-playlists",
        json={
            "name": "list-source",
            "url": "http://provider",
            "username": "u1",
            "password": "playlist-secret",
        },
    )
    assert save_playlist.status_code == 200

    backup = source_client.get("/backup/download")
    assert backup.status_code == 200
    payload = json.loads(backup.data.decode("utf-8"))
    assert payload["profiles"][0]["password"] == "source-secret"
    assert payload["saved_playlists"][0]["config"]["password"] == "playlist-secret"

    base_dir = source["paths"]["CREDENTIAL_PROFILE_STORE"].parent
    target = app_factory(
        CREDENTIAL_PROFILE_STORE=str(Path(base_dir) / "target_profiles.json"),
        PLAYLIST_STORE_PATH=str(Path(base_dir) / "target_playlists.json"),
        AUTH_STORE_PATH=str(Path(base_dir) / "target_auth.json"),
        AUTH_THROTTLE_STORE_PATH=str(Path(base_dir) / "target_throttle.json"),
        FLASK_SECRET_FILE=str(Path(base_dir) / "target_flask_secret"),
        CREDENTIAL_CIPHER_FILE=str(Path(base_dir) / "target_cipher_key"),
    )
    target_client = target["client"]

    target_setup = target_client.post("/auth/setup", json={"username": "admin", "password": "password123"})
    assert target_setup.status_code == 200

    restore = target_client.post(
        "/backup/restore",
        data={"file": (io.BytesIO(json.dumps(payload).encode("utf-8")), "backup.json")},
        content_type="multipart/form-data",
    )
    assert restore.status_code == 200
    assert restore.json["ok"] is True

    restored_profiles = target_client.get("/profiles")
    assert restored_profiles.status_code == 200
    assert restored_profiles.json["profiles"][0]["password"] == "source-secret"

    restored_playlist = target_client.get(f"/saved-playlists/{payload['saved_playlists'][0]['id']}")
    assert restored_playlist.status_code == 200
    assert restored_playlist.json["config"]["password"] == "playlist-secret"
