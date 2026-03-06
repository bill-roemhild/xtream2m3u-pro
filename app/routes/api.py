"""API routes for Xtream Codes proxy (categories, M3U, XMLTV)"""
import json
import logging
import os
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, Response, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from app.services import (
    build_stream_link_candidates,
    build_stream_link,
    fetch_api_data,
    fetch_categories_and_channels,
    generate_m3u_playlist,
    normalize_server_info,
    normalize_user_info,
    validate_xtream_credentials,
)
from app.utils import encode_url, group_matches, parse_group_list

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)
PROFILE_STORE_PATH = Path(os.environ.get("CREDENTIAL_PROFILE_STORE", "/data/credential_profiles.json"))
PLAYLIST_STORE_PATH = Path(os.environ.get("PLAYLIST_STORE_PATH", "/data/saved_playlists.json"))
AUTH_STORE_PATH = Path(os.environ.get("AUTH_STORE_PATH", "/data/auth_users.json"))
AUTH_THROTTLE_STORE_PATH = Path(os.environ.get("AUTH_THROTTLE_STORE_PATH", "/data/auth_login_throttle.json"))
AUTH_MAX_LOGIN_ATTEMPTS = max(1, int(os.environ.get("AUTH_MAX_LOGIN_ATTEMPTS", "5")))
AUTH_LOCKOUT_SECONDS = max(10, int(os.environ.get("AUTH_LOCKOUT_SECONDS", "300")))
AUTH_ATTEMPT_WINDOW_SECONDS = max(10, int(os.environ.get("AUTH_ATTEMPT_WINDOW_SECONDS", "300")))
CREDENTIAL_CIPHER_FILE = Path(os.environ.get("CREDENTIAL_CIPHER_FILE", "/data/credential_cipher_key"))
CREDENTIAL_CIPHER_PREFIX = "enc::v1::"


def _load_or_create_credential_cipher():
    env_key = os.environ.get("CREDENTIAL_CIPHER_KEY", "").strip()
    key = None
    if env_key:
        key = env_key.encode("utf-8")
    else:
        try:
            if CREDENTIAL_CIPHER_FILE.exists():
                file_value = CREDENTIAL_CIPHER_FILE.read_text(encoding="utf-8").strip()
                if file_value:
                    key = file_value.encode("utf-8")
            if not key:
                CREDENTIAL_CIPHER_FILE.parent.mkdir(parents=True, exist_ok=True)
                key = Fernet.generate_key()
                CREDENTIAL_CIPHER_FILE.write_text(key.decode("utf-8"), encoding="utf-8")
        except Exception as error:
            logger.warning("Failed to load credential cipher key at %s: %s", CREDENTIAL_CIPHER_FILE, error)
            key = Fernet.generate_key()
    return Fernet(key)


CREDENTIAL_CIPHER = _load_or_create_credential_cipher()


def _encrypt_secret(value):
    raw = str(value or "")
    if not raw:
        return ""
    if raw.startswith(CREDENTIAL_CIPHER_PREFIX):
        return raw
    token = CREDENTIAL_CIPHER.encrypt(raw.encode("utf-8")).decode("utf-8")
    return f"{CREDENTIAL_CIPHER_PREFIX}{token}"


def _decrypt_secret(value):
    raw = str(value or "")
    if not raw:
        return ""
    if not raw.startswith(CREDENTIAL_CIPHER_PREFIX):
        return raw
    token = raw[len(CREDENTIAL_CIPHER_PREFIX):]
    try:
        return CREDENTIAL_CIPHER.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.warning("Failed decrypting stored credential secret; returning empty value")
        return ""


def _sanitize_throttle_store(raw_data):
    now_ts = int(time.time())
    entries = {}
    if isinstance(raw_data, dict):
        candidate = raw_data.get("entries", {})
        if isinstance(candidate, dict):
            for key, entry in candidate.items():
                if not isinstance(entry, dict):
                    continue
                failures = [
                    int(ts)
                    for ts in (entry.get("failures") or [])
                    if str(ts).isdigit()
                ]
                failures = [ts for ts in failures if ts >= now_ts - max(AUTH_ATTEMPT_WINDOW_SECONDS * 2, 3600)]
                locked_until = int(entry.get("locked_until", 0) or 0)
                if failures or locked_until > now_ts:
                    entries[str(key)] = {
                        "failures": failures,
                        "locked_until": locked_until,
                    }
    return {"entries": entries}


def load_throttle_store():
    try:
        if AUTH_THROTTLE_STORE_PATH.exists():
            raw = json.loads(AUTH_THROTTLE_STORE_PATH.read_text(encoding="utf-8"))
            data = _sanitize_throttle_store(raw)
        else:
            data = {"entries": {}}
    except Exception as error:
        logger.warning("Failed reading auth throttle store path=%s error=%s", AUTH_THROTTLE_STORE_PATH, error)
        data = {"entries": {}}
    save_throttle_store(data)
    return data


def save_throttle_store(data):
    AUTH_THROTTLE_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_THROTTLE_STORE_PATH.write_text(
        json.dumps(_sanitize_throttle_store(data), indent=2),
        encoding="utf-8",
    )


def _client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return str(forwarded_for).split(",")[0].strip()
    return str(request.remote_addr or "unknown").strip()


def _login_throttle_key(username):
    return f"{str(username or '').strip().lower()}|{_client_ip()}"


def _check_login_lockout(username):
    key = _login_throttle_key(username)
    now_ts = int(time.time())
    throttle = load_throttle_store()
    entry = throttle.get("entries", {}).get(key, {"failures": [], "locked_until": 0})
    locked_until = int(entry.get("locked_until", 0) or 0)
    if locked_until > now_ts:
        retry_after = max(1, locked_until - now_ts)
        return True, retry_after
    return False, 0


def _record_login_failure(username):
    key = _login_throttle_key(username)
    now_ts = int(time.time())
    throttle = load_throttle_store()
    entry = throttle.setdefault("entries", {}).setdefault(key, {"failures": [], "locked_until": 0})
    window_start = now_ts - AUTH_ATTEMPT_WINDOW_SECONDS
    failures = [int(ts) for ts in (entry.get("failures") or []) if int(ts) >= window_start]
    failures.append(now_ts)
    entry["failures"] = failures
    if len(failures) >= AUTH_MAX_LOGIN_ATTEMPTS:
        entry["locked_until"] = now_ts + AUTH_LOCKOUT_SECONDS
        entry["failures"] = []
    save_throttle_store(throttle)


def _clear_login_failures(username):
    uname = str(username or "").strip().lower()
    if not uname:
        return
    throttle = load_throttle_store()
    keys = [key for key in throttle.get("entries", {}).keys() if key.startswith(f"{uname}|")]
    for key in keys:
        throttle["entries"].pop(key, None)
    save_throttle_store(throttle)


def _sanitize_auth_store(raw_data):
    users = []
    if isinstance(raw_data, dict) and isinstance(raw_data.get("users"), list):
        for user in raw_data["users"]:
            if not isinstance(user, dict):
                continue
            username = str(user.get("username", "")).strip()
            password_hash = str(user.get("password_hash", "")).strip()
            if not username or not password_hash:
                continue
            users.append(
                {
                    "username": username,
                    "password_hash": password_hash,
                    "is_admin": bool(user.get("is_admin", False)),
                    "created_at": int(user.get("created_at", int(time.time()))),
                }
            )
    return {"users": users}


def load_auth_store():
    try:
        if AUTH_STORE_PATH.exists():
            raw = json.loads(AUTH_STORE_PATH.read_text(encoding="utf-8"))
            data = _sanitize_auth_store(raw)
        else:
            data = {"users": []}
    except Exception as error:
        logger.warning("Failed reading auth store path=%s error=%s", AUTH_STORE_PATH, error)
        data = {"users": []}
    save_auth_store(data)
    return data


def save_auth_store(data):
    AUTH_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_STORE_PATH.write_text(json.dumps(_sanitize_auth_store(data), indent=2), encoding="utf-8")


def _find_user(username, auth_store):
    target = str(username).strip()
    return next((u for u in auth_store.get("users", []) if u.get("username") == target), None)


def _is_authenticated():
    return bool(session.get("authenticated")) and bool(session.get("username"))


def _current_username():
    return str(session.get("username", "")).strip()


def _is_admin():
    return bool(session.get("is_admin"))


def _delete_owned_records(username):
    owner = str(username).strip()
    if not owner:
        return 0, 0

    profiles = load_profiles()
    kept_profiles = [p for p in profiles if str(p.get("owner", "")).strip() != owner]
    deleted_profiles = len(profiles) - len(kept_profiles)
    if deleted_profiles:
        save_profiles(kept_profiles)

    playlists = load_saved_playlists()
    kept_playlists = [p for p in playlists if str(p.get("owner", "")).strip() != owner]
    deleted_playlists = len(playlists) - len(kept_playlists)
    if deleted_playlists:
        save_saved_playlists(kept_playlists)

    return deleted_profiles, deleted_playlists


def _build_backup_payload():
    return {
        "version": 1,
        "generated_at": int(time.time()),
        "auth_users": load_auth_store().get("users", []),
        "profiles": load_profiles_for_backup(),
        "saved_playlists": load_saved_playlists_for_backup(),
    }


@api_bp.before_request
def require_authentication():
    """Protect API routes behind login/setup flow."""
    if request.method == "OPTIONS":
        return None

    public_endpoints = {
        "api.auth_status",
        "api.auth_setup",
        "api.auth_login",
        "api.generate_m3u",
        "api.generate_xmltv",
        "api.generate_saved_playlist",
        "api.generate_saved_xmltv",
    }
    if request.endpoint in public_endpoints:
        return None

    auth_store = load_auth_store()
    has_users = len(auth_store.get("users", [])) > 0
    if not has_users:
        return jsonify({"error": "Setup Required", "details": "Create the first admin account first"}), 403
    if not _is_authenticated():
        return jsonify({"error": "Unauthorized", "details": "Login required"}), 401
    return None


@api_bp.route("/auth/status", methods=["GET"])
def auth_status():
    auth_store = load_auth_store()
    users = auth_store.get("users", [])
    return jsonify(
        {
            "needs_setup": len(users) == 0,
            "authenticated": _is_authenticated(),
            "username": session.get("username"),
            "is_admin": bool(session.get("is_admin")),
            "user_count": len(users),
        }
    )


@api_bp.route("/auth/setup", methods=["POST"])
def auth_setup():
    auth_store = load_auth_store()
    if len(auth_store.get("users", [])) > 0:
        return jsonify({"error": "Setup Complete", "details": "Admin account already exists"}), 409

    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username or not password:
        return jsonify({"error": "Missing Parameters", "details": "Required: username, password"}), 400
    if len(password) < 8:
        return jsonify({"error": "Weak Password", "details": "Password must be at least 8 characters"}), 400

    auth_store["users"].append(
        {
            "username": username,
            "password_hash": generate_password_hash(password),
            "is_admin": True,
            "created_at": int(time.time()),
        }
    )
    save_auth_store(auth_store)
    session["authenticated"] = True
    session["username"] = username
    session["is_admin"] = True
    return jsonify({"ok": True, "username": username, "is_admin": True})


@api_bp.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username or not password:
        return jsonify({"error": "Missing Parameters", "details": "Required: username, password"}), 400

    locked, retry_after = _check_login_lockout(username)
    if locked:
        return (
            jsonify(
                {
                    "error": "Too Many Attempts",
                    "details": f"Too many failed login attempts. Try again in {retry_after} seconds.",
                    "retry_after": retry_after,
                }
            ),
            429,
            {"Retry-After": str(retry_after)},
        )

    auth_store = load_auth_store()
    user = _find_user(username, auth_store)
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        _record_login_failure(username)
        return jsonify({"error": "Invalid Credentials", "details": "Incorrect username or password"}), 401

    _clear_login_failures(username)
    session["authenticated"] = True
    session["username"] = user["username"]
    session["is_admin"] = bool(user.get("is_admin"))
    return jsonify({"ok": True, "username": user["username"], "is_admin": bool(user.get("is_admin"))})


@api_bp.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@api_bp.route("/auth/users", methods=["POST"])
def auth_create_user():
    if not bool(session.get("is_admin")):
        return jsonify({"error": "Forbidden", "details": "Admin privileges required"}), 403

    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    is_admin = bool(data.get("is_admin", False))
    if not username or not password:
        return jsonify({"error": "Missing Parameters", "details": "Required: username, password"}), 400
    if len(password) < 8:
        return jsonify({"error": "Weak Password", "details": "Password must be at least 8 characters"}), 400

    auth_store = load_auth_store()
    if _find_user(username, auth_store):
        return jsonify({"error": "Conflict", "details": "Username already exists"}), 409

    auth_store["users"].append(
        {
            "username": username,
            "password_hash": generate_password_hash(password),
            "is_admin": is_admin,
            "created_at": int(time.time()),
        }
    )
    save_auth_store(auth_store)
    return jsonify({"ok": True, "username": username, "is_admin": is_admin})


@api_bp.route("/auth/users", methods=["GET"])
def auth_list_users():
    if not _is_admin():
        return jsonify({"error": "Forbidden", "details": "Admin privileges required"}), 403

    auth_store = load_auth_store()
    users = [
        {
            "username": str(user.get("username", "")).strip(),
            "is_admin": bool(user.get("is_admin", False)),
            "created_at": int(user.get("created_at", int(time.time()))),
        }
        for user in auth_store.get("users", [])
    ]
    users.sort(key=lambda user: user["username"].lower())
    return jsonify({"users": users})


@api_bp.route("/auth/users/delete", methods=["POST"])
def auth_delete_user():
    if not _is_admin():
        return jsonify({"error": "Forbidden", "details": "Admin privileges required"}), 403

    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    if not username:
        return jsonify({"error": "Missing Parameters", "details": "Required: username"}), 400

    if username == _current_username():
        return jsonify({"error": "Forbidden", "details": "You cannot delete your own account"}), 403

    auth_store = load_auth_store()
    users = auth_store.get("users", [])
    target_user = next((user for user in users if str(user.get("username", "")).strip() == username), None)
    if not target_user:
        return jsonify({"error": "Not Found", "details": "User not found"}), 404

    if bool(target_user.get("is_admin")):
        admin_count = sum(1 for user in users if bool(user.get("is_admin")))
        if admin_count <= 1:
            return jsonify({"error": "Conflict", "details": "Cannot delete the last admin account"}), 409

    auth_store["users"] = [user for user in users if str(user.get("username", "")).strip() != username]
    save_auth_store(auth_store)
    deleted_profiles, deleted_playlists = _delete_owned_records(username)
    return jsonify(
        {
            "ok": True,
            "username": username,
            "deleted_profiles": deleted_profiles,
            "deleted_playlists": deleted_playlists,
        }
    )


@api_bp.route("/backup/download", methods=["GET"])
def backup_download():
    if not _is_admin():
        return jsonify({"error": "Forbidden", "details": "Admin privileges required"}), 403

    payload = _build_backup_payload()
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime(payload["generated_at"]))
    filename = f"xtream2m3u-backup-{ts}.json"
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_bp.route("/backup/restore", methods=["POST"])
def backup_restore():
    if not _is_admin():
        return jsonify({"error": "Forbidden", "details": "Admin privileges required"}), 403

    backup_file = request.files.get("file")
    if not backup_file:
        return jsonify({"error": "Missing Parameters", "details": "Required: file"}), 400

    try:
        raw_content = backup_file.read()
        data = json.loads(raw_content.decode("utf-8"))
    except Exception:
        return jsonify({"error": "Invalid Backup", "details": "Backup file is not valid JSON"}), 400

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid Backup", "details": "Backup payload must be a JSON object"}), 400

    auth_users = data.get("auth_users", [])
    profiles = data.get("profiles", [])
    saved_playlists = data.get("saved_playlists", [])

    if not isinstance(auth_users, list) or not isinstance(profiles, list) or not isinstance(saved_playlists, list):
        return jsonify({"error": "Invalid Backup", "details": "Backup fields must be arrays"}), 400

    # Save all stores through existing sanitizers.
    save_auth_store({"users": auth_users})
    save_profiles(profiles)
    save_saved_playlists(saved_playlists)

    restored_auth = load_auth_store().get("users", [])
    current_user = _current_username()
    current_exists = any(str(user.get("username", "")).strip() == current_user for user in restored_auth)
    relogin_required = not current_exists
    if relogin_required:
        session.clear()
    else:
        current = next(
            (user for user in restored_auth if str(user.get("username", "")).strip() == current_user),
            None,
        )
        session["authenticated"] = True
        session["username"] = current_user
        session["is_admin"] = bool(current.get("is_admin", False)) if current else False

    return jsonify(
        {
            "ok": True,
            "restored": {
                "users": len(restored_auth),
                "profiles": len(load_profiles()),
                "saved_playlists": len(load_saved_playlists()),
            },
            "relogin_required": relogin_required,
        }
    )


def parse_stream_id_list(raw_value):
    """Parse comma-delimited stream ids into normalized string list."""
    if isinstance(raw_value, list):
        values = raw_value
    else:
        values = parse_group_list(str(raw_value or ""))
    return [str(v).strip() for v in values if str(v).strip()]


def build_subscription_details(user_data):
    """Build a safe, normalized subscription payload for UI consumption."""
    user_info = normalize_user_info(user_data.get("user_info", {}))
    server_info = normalize_server_info(user_data.get("server_info", {}))

    return {
        "profile": user_info,
        "server": server_info,
        "status": user_info["status"],
        "exp_date": user_info["exp_date"],
        "created_at": user_info["created_at"],
        "is_trial": user_info["is_trial"],
        "active_cons": user_info["active_cons"],
        "max_connections": user_info["max_connections"],
        "allowed_output_formats": user_info["allowed_output_formats"],
        "server_url": server_info["url"],
        "server_port": server_info["port"],
        "server_timezone": server_info["timezone"],
        "server_time_now": server_info["time_now"],
    }


def sanitize_profiles(raw_profiles):
    """Normalize profile data."""
    cleaned = []
    seen_names = set()

    if isinstance(raw_profiles, list):
        for profile in raw_profiles:
            if not isinstance(profile, dict):
                continue
            name = str(profile.get("name", "")).strip()
            owner = str(profile.get("owner", "")).strip()
            dedupe_key = f"{owner}::{name}"
            if not name or dedupe_key in seen_names:
                continue
            seen_names.add(dedupe_key)
            cleaned.append(
                {
                    "name": name,
                    "url": str(profile.get("url", "")).strip(),
                    "username": str(profile.get("username", "")).strip(),
                    "password": _decrypt_secret(profile.get("password", "")),
                    "include_vod": str(profile.get("include_vod", "false")).lower() in ("1", "true", "yes", "on"),
                    "owner": owner,
                }
            )

    return cleaned


def save_profiles(profiles):
    """Persist profiles to container-backed file."""
    PROFILE_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = sanitize_profiles(profiles)
    payload_for_storage = []
    for profile in payload:
        item = dict(profile)
        item["password"] = _encrypt_secret(item.get("password", ""))
        payload_for_storage.append(item)
    PROFILE_STORE_PATH.write_text(json.dumps(payload_for_storage, indent=2), encoding="utf-8")


def load_profiles():
    """Load profiles from container-backed file."""
    try:
        if PROFILE_STORE_PATH.exists():
            raw = json.loads(PROFILE_STORE_PATH.read_text(encoding="utf-8"))
            profiles = sanitize_profiles(raw)
        else:
            profiles = []
    except Exception as error:
        logger.warning("Failed to read profile store path=%s error=%s", PROFILE_STORE_PATH, error)
        profiles = []

    save_profiles(profiles)
    return profiles


def load_profiles_for_backup():
    """Load profiles for backup export with decrypted secrets for cross-instance portability."""
    try:
        if PROFILE_STORE_PATH.exists():
            raw = json.loads(PROFILE_STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return sanitize_profiles(raw)
    except Exception as error:
        logger.warning("Failed reading raw profile store for backup path=%s error=%s", PROFILE_STORE_PATH, error)
    return []


def sanitize_saved_playlists(raw_items):
    """Normalize saved playlist presets."""
    if not isinstance(raw_items, list):
        return []

    cleaned = []
    seen_ids = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        playlist_id = str(item.get("id", "")).strip()
        if not playlist_id or playlist_id in seen_ids:
            continue
        seen_ids.add(playlist_id)
        cleaned.append(
            {
                "id": playlist_id,
                "name": str(item.get("name", "")).strip() or f"Playlist {playlist_id[:6]}",
                "created_at": int(item.get("created_at", int(time.time()))),
                "config": (
                    {
                        **item.get("config"),
                        "password": _decrypt_secret((item.get("config") or {}).get("password", "")),
                    }
                    if isinstance(item.get("config"), dict)
                    else {}
                ),
                "owner": str(item.get("owner", "")).strip(),
            }
        )
    return cleaned


def save_saved_playlists(items):
    """Persist saved playlist presets."""
    PLAYLIST_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned = sanitize_saved_playlists(items)
    payload_for_storage = []
    for item in cleaned:
        next_item = dict(item)
        config = dict(next_item.get("config") or {})
        config["password"] = _encrypt_secret(config.get("password", ""))
        next_item["config"] = config
        payload_for_storage.append(next_item)
    PLAYLIST_STORE_PATH.write_text(
        json.dumps(payload_for_storage, indent=2),
        encoding="utf-8",
    )


def load_saved_playlists():
    """Load saved playlist presets."""
    try:
        if PLAYLIST_STORE_PATH.exists():
            raw = json.loads(PLAYLIST_STORE_PATH.read_text(encoding="utf-8"))
            items = sanitize_saved_playlists(raw)
        else:
            items = []
    except Exception as error:
        logger.warning("Failed to read playlist store path=%s error=%s", PLAYLIST_STORE_PATH, error)
        items = []

    save_saved_playlists(items)
    return items


def load_saved_playlists_for_backup():
    """Load saved playlists for backup export with decrypted secrets for cross-instance portability."""
    try:
        if PLAYLIST_STORE_PATH.exists():
            raw = json.loads(PLAYLIST_STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return sanitize_saved_playlists(raw)
    except Exception as error:
        logger.warning("Failed reading raw playlist store for backup path=%s error=%s", PLAYLIST_STORE_PATH, error)
    return []


def build_playlist_from_config(config):
    """Generate M3U playlist text from saved/current config payload."""
    url = config.get("url")
    username = config.get("username")
    password = config.get("password")
    proxy_url = request.host_url.rstrip("/")
    if not url or not username or not password:
        return None, None, {"error": "Missing Parameters", "details": "Required: url, username, password"}, 400

    wanted_groups = parse_group_list(config.get("wanted_groups", ""))
    unwanted_groups = parse_group_list(config.get("unwanted_groups", ""))
    wanted_stream_ids = parse_stream_id_list(config.get("wanted_stream_ids", ""))
    unwanted_stream_ids = parse_stream_id_list(config.get("unwanted_stream_ids", ""))
    no_stream_proxy = False
    include_vod = str(config.get("include_vod", "false")).lower() == "true"
    include_channel_id = str(config.get("include_channel_id", "false")).lower() == "true"
    channel_id_tag = str(config.get("channel_id_tag", "channel-id"))

    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        if isinstance(error_json, str):
            try:
                error_json = json.loads(error_json)
            except json.JSONDecodeError:
                error_json = {"error": "Validation Error", "details": error_json}
        return None, None, error_json, error_code

    categories, streams, error_json, error_code = fetch_categories_and_channels(url, username, password, include_vod)
    if error_json:
        if isinstance(error_json, str):
            try:
                error_json = json.loads(error_json)
            except json.JSONDecodeError:
                error_json = {"error": "Fetch Error", "details": error_json}
        return None, None, error_json, error_code

    username = user_data["user_info"]["username"]
    password = user_data["user_info"]["password"]
    server_url = f"http://{user_data['server_info']['url']}:{user_data['server_info']['port']}"

    m3u_playlist = generate_m3u_playlist(
        url=url,
        username=username,
        password=password,
        server_url=server_url,
        categories=categories,
        streams=streams,
        wanted_groups=wanted_groups,
        unwanted_groups=unwanted_groups,
        wanted_stream_ids=wanted_stream_ids,
        unwanted_stream_ids=unwanted_stream_ids,
        no_stream_proxy=no_stream_proxy,
        include_vod=include_vod,
        include_channel_id=include_channel_id,
        channel_id_tag=channel_id_tag,
        proxy_url=proxy_url
    )
    filename = "FullPlaylist.m3u" if include_vod else "LiveStream.m3u"
    return m3u_playlist, filename, None, None


def _filter_live_streams_for_groups(categories, streams, wanted_groups, unwanted_groups, wanted_stream_ids=None, unwanted_stream_ids=None):
    """Return filtered live streams matching include/exclude group logic."""
    category_names = {str(cat.get("category_id")): str(cat.get("category_name", "Uncategorized")) for cat in categories}
    wanted_stream_ids = {str(v).strip() for v in (wanted_stream_ids or []) if str(v).strip()}
    unwanted_stream_ids = {str(v).strip() for v in (unwanted_stream_ids or []) if str(v).strip()}
    filtered = []
    for stream in streams:
        if stream.get("content_type") != "live":
            continue
        category_name = category_names.get(str(stream.get("category_id")), "Uncategorized")
        stream_id = str(stream.get("stream_id") or "").strip()
        has_wanted = bool(wanted_groups or wanted_stream_ids)
        if has_wanted:
            if wanted_stream_ids:
                include_stream = stream_id in wanted_stream_ids
            else:
                include_stream = any(group_matches(category_name, pattern) for pattern in (wanted_groups or []))
        else:
            include_stream = True
        if include_stream and (unwanted_groups or unwanted_stream_ids):
            include_stream = not (
                any(group_matches(category_name, pattern) for pattern in (unwanted_groups or []))
                or stream_id in unwanted_stream_ids
            )
        if include_stream:
            filtered.append(stream)
    return filtered


def _filter_xmltv_by_channel_ids(xmltv_data, allowed_channel_ids):
    """Filter XMLTV by allowed channel IDs."""
    if not allowed_channel_ids:
        return '<?xml version="1.0" encoding="UTF-8"?><tv></tv>'
    try:
        root = ET.fromstring(xmltv_data)
    except ET.ParseError as error:
        logger.warning("Failed parsing XMLTV for filtering: %s", error)
        return xmltv_data

    allowed = set(allowed_channel_ids)
    for channel in list(root.findall("channel")):
        if channel.get("id") not in allowed:
            root.remove(channel)
    for programme in list(root.findall("programme")):
        if programme.get("channel") not in allowed:
            root.remove(programme)
    return ET.tostring(root, encoding="unicode")


def build_xmltv_from_config(config):
    """Generate filtered XMLTV text from saved/current config payload."""
    url = config.get("url")
    username = config.get("username")
    password = config.get("password")
    if not url or not username or not password:
        return None, {"error": "Missing Parameters", "details": "Required: url, username, password"}, 400

    xmltv_url = f"{url.rstrip('/')}/xmltv.php?username={username}&password={password}"
    xmltv_data = fetch_api_data(xmltv_url, timeout=20)
    if isinstance(xmltv_data, tuple):
        return None, xmltv_data[0], xmltv_data[1]

    wanted_groups = parse_group_list(config.get("wanted_groups", ""))
    unwanted_groups = parse_group_list(config.get("unwanted_groups", ""))
    wanted_stream_ids = parse_stream_id_list(config.get("wanted_stream_ids", ""))
    unwanted_stream_ids = parse_stream_id_list(config.get("unwanted_stream_ids", ""))
    if wanted_groups or unwanted_groups or wanted_stream_ids or unwanted_stream_ids:
        categories, streams, error_json, error_code = fetch_categories_and_channels(url, username, password, include_vod=False)
        if error_json:
            if isinstance(error_json, str):
                try:
                    error_json = json.loads(error_json)
                except json.JSONDecodeError:
                    error_json = {"error": "Filter Error", "details": error_json}
            return None, error_json, error_code

        live_streams = _filter_live_streams_for_groups(
            categories,
            streams,
            wanted_groups,
            unwanted_groups,
            wanted_stream_ids=wanted_stream_ids,
            unwanted_stream_ids=unwanted_stream_ids,
        )
        allowed_channel_ids = {
            str(stream.get("epg_channel_id")).strip()
            for stream in live_streams
            if str(stream.get("epg_channel_id", "")).strip()
        }
        xmltv_data = _filter_xmltv_by_channel_ids(xmltv_data, allowed_channel_ids)

    return xmltv_data, None, None


def get_required_params():
    """Get and validate the required parameters from the request (supports both GET and POST)"""
    # Handle both GET and POST requests
    if request.method == "POST":
        data = request.get_json() or {}
        url = data.get("url")
        username = data.get("username")
        password = data.get("password")
        proxy_url = data.get("proxy_url") or request.host_url.rstrip("/")
    else:
        url = request.args.get("url")
        username = request.args.get("username")
        password = request.args.get("password")
        proxy_url = request.args.get("proxy_url") or request.host_url.rstrip("/")

    if not url or not username or not password:
        return (
            None,
            None,
            None,
            None,
            jsonify({"error": "Missing Parameters", "details": "Required parameters: url, username, and password"}),
            400
        )

    return url, username, password, proxy_url, None, None


@api_bp.route("/subscription", methods=["GET"])
def get_subscription():
    """Get subscription details from Xtream player_api."""
    url, username, password, _proxy_url, error, status_code = get_required_params()
    if error:
        logger.warning("Subscription request missing required parameters")
        return error, status_code

    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        logger.warning(
            "Subscription lookup failed for url=%s username=%s error_code=%s error=%s",
            url,
            username,
            error_code,
            error_json,
        )
        return error_json, error_code, {"Content-Type": "application/json"}

    details = build_subscription_details(user_data)
    return jsonify(details)


@api_bp.route("/profiles", methods=["GET"])
def get_profiles():
    """Get saved credential profiles."""
    all_profiles = load_profiles()
    if _is_admin():
        profiles = all_profiles
    else:
        current_user = _current_username()
        profiles = [p for p in all_profiles if str(p.get("owner", "")).strip() == current_user]

    logger.info(
        "Loaded %s/%s credential profiles from %s for user=%s admin=%s",
        len(profiles),
        len(all_profiles),
        PROFILE_STORE_PATH,
        _current_username(),
        _is_admin(),
    )
    return jsonify({"profiles": profiles, "store_path": str(PROFILE_STORE_PATH)})


@api_bp.route("/profiles", methods=["POST"])
def save_profile():
    """Create or update a credential profile."""
    data = request.get_json() or {}
    name = str(data.get("name", "")).strip()
    url = str(data.get("url", "")).strip()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    include_vod = str(data.get("include_vod", "false")).lower() in ("1", "true", "yes", "on")
    target_owner = str(data.get("owner", "")).strip()
    current_user = _current_username()

    if not name or not url or not username or not password:
        return jsonify({"error": "Missing Parameters", "details": "Required: name, url, username, password"}), 400

    profiles = load_profiles()
    if _is_admin():
        owner_for_match = target_owner
    else:
        owner_for_match = current_user

    existing = next((p for p in profiles if p["name"] == name and str(p.get("owner", "")).strip() == owner_for_match), None)
    if existing:
        existing.update(
            {
                "url": url,
                "username": username,
                "password": password,
                "include_vod": include_vod,
                "owner": str(existing.get("owner", "")).strip() or owner_for_match or current_user,
            }
        )
    else:
        owner_for_new = owner_for_match or current_user
        profiles.append(
            {
                "name": name,
                "url": url,
                "username": username,
                "password": password,
                "include_vod": include_vod,
                "owner": owner_for_new,
            }
        )

    save_profiles(profiles)
    visible_profiles = load_profiles() if _is_admin() else [p for p in load_profiles() if str(p.get("owner", "")).strip() == current_user]
    logger.info("Saved credential profile name=%s url=%s username=%s owner=%s", name, url, username, current_user)
    return jsonify({"ok": True, "profiles": visible_profiles})


@api_bp.route("/profiles/delete", methods=["POST"])
def delete_profile():
    """Delete a credential profile."""
    data = request.get_json() or {}
    name = str(data.get("name", "")).strip()
    target_owner = str(data.get("owner", "")).strip()
    if not name:
        return jsonify({"error": "Missing Parameters", "details": "Required: name"}), 400

    current_user = _current_username()
    profiles = load_profiles()
    if _is_admin():
        if target_owner:
            filtered = [p for p in profiles if not (p["name"] == name and str(p.get("owner", "")).strip() == target_owner)]
        else:
            filtered = [p for p in profiles if p["name"] != name]
    else:
        filtered = [
            p for p in profiles
            if not (p["name"] == name and str(p.get("owner", "")).strip() == current_user)
        ]
    if len(filtered) == len(profiles):
        return jsonify({"error": "Not Found", "details": "Profile not found"}), 404

    save_profiles(filtered)
    visible_profiles = load_profiles() if _is_admin() else [p for p in load_profiles() if str(p.get("owner", "")).strip() == current_user]
    logger.info("Deleted credential profile name=%s by user=%s admin=%s", name, current_user, _is_admin())
    return jsonify({"ok": True, "profiles": visible_profiles})


@api_bp.route("/saved-playlists", methods=["GET"])
def list_saved_playlists():
    """List saved playlist presets."""
    all_items = load_saved_playlists()
    is_admin = _is_admin()
    if is_admin:
        items = all_items
    else:
        current_user = _current_username()
        items = [item for item in all_items if str(item.get("owner", "")).strip() == current_user]

    service_url = (request.args.get("url") or "").strip()
    service_username = (request.args.get("username") or "").strip()
    service_owner = (request.args.get("owner") or "").strip()
    if is_admin and service_owner:
        items = [item for item in items if str(item.get("owner", "")).strip() == service_owner]

    if service_url and service_username:
        items = [
            item for item in items
            if str(item.get("config", {}).get("url", "")).strip() == service_url
            and str(item.get("config", {}).get("username", "")).strip() == service_username
        ]

    base = request.host_url.rstrip("/")
    return jsonify(
        {
            "items": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "owner": str(item.get("owner", "")).strip(),
                    "created_at": item["created_at"],
                    "url": f"{base}/playlist/{item['id']}/m3u",
                    "m3u_url": f"{base}/playlist/{item['id']}/m3u",
                    "xmltv_url": f"{base}/playlist/{item['id']}/xmltv",
                }
                for item in items
            ],
            "store_path": str(PLAYLIST_STORE_PATH),
        }
    )


@api_bp.route("/saved-playlists/delete", methods=["POST"])
def delete_saved_playlist():
    """Delete a saved playlist preset by id."""
    data = request.get_json() or {}
    playlist_id = str(data.get("id", "")).strip()
    if not playlist_id:
        return jsonify({"error": "Missing Parameters", "details": "Required: id"}), 400

    current_user = _current_username()
    items = load_saved_playlists()
    if _is_admin():
        filtered = [item for item in items if item.get("id") != playlist_id]
    else:
        filtered = [
            item for item in items
            if not (
                item.get("id") == playlist_id and str(item.get("owner", "")).strip() == current_user
            )
        ]
    if len(filtered) == len(items):
        return jsonify({"error": "Not Found", "details": "Saved playlist not found"}), 404

    save_saved_playlists(filtered)
    return jsonify({"ok": True})


@api_bp.route("/saved-playlists", methods=["POST"])
def save_playlist_preset():
    """Create or update a playlist configuration and return simplified URLs."""
    data = request.get_json() or {}
    name = str(data.get("name", "")).strip()
    requested_id = str(data.get("id", "")).strip()
    if not name:
        return jsonify({"error": "Missing Parameters", "details": "Required: name"}), 400

    config = {
        "url": data.get("url"),
        "username": data.get("username"),
        "password": data.get("password"),
        "proxy_url": "",
        "wanted_groups": data.get("wanted_groups", ""),
        "unwanted_groups": data.get("unwanted_groups", ""),
        "wanted_stream_ids": data.get("wanted_stream_ids", ""),
        "unwanted_stream_ids": data.get("unwanted_stream_ids", ""),
        "nostreamproxy": True,
        "include_vod": str(data.get("include_vod", "false")).lower() == "true",
        "include_channel_id": str(data.get("include_channel_id", "false")).lower() == "true",
        "channel_id_tag": str(data.get("channel_id_tag", "channel-id")),
    }
    if not config["url"] or not config["username"] or not config["password"]:
        return jsonify({"error": "Missing Parameters", "details": "Required: url, username, password"}), 400

    current_user = _current_username()
    requested_owner = str(data.get("owner", "")).strip()
    owner_for_item = requested_owner if (_is_admin() and requested_owner) else current_user
    items = load_saved_playlists()
    existing = (
        next(
            (
                item for item in items
                if item.get("id") == requested_id
                and (_is_admin() or str(item.get("owner", "")).strip() == current_user)
            ),
            None,
        )
        if requested_id else None
    )
    if existing:
        existing["name"] = name
        existing["config"] = config
        existing["owner"] = owner_for_item or str(existing.get("owner", "")).strip() or current_user
        playlist_id = existing["id"]
        item_name = existing["name"]
        item_owner = existing["owner"]
    else:
        playlist_id = uuid.uuid4().hex[:12]
        item = {
            "id": playlist_id,
            "name": name,
            "created_at": int(time.time()),
            "config": config,
            "owner": owner_for_item,
        }
        items.append(item)
        item_name = item["name"]
        item_owner = item["owner"]

    save_saved_playlists(items)

    base = request.host_url.rstrip('/')
    m3u_url = f"{base}/playlist/{playlist_id}/m3u"
    xmltv_url = f"{base}/playlist/{playlist_id}/xmltv"
    return jsonify(
        {
            "ok": True,
            "id": playlist_id,
            "name": item_name,
            "owner": item_owner,
            "url": m3u_url,
            "m3u_url": m3u_url,
            "xmltv_url": xmltv_url,
        }
    )


@api_bp.route("/saved-playlists/<playlist_id>", methods=["GET"])
def get_saved_playlist(playlist_id):
    """Get saved playlist details by id."""
    items = load_saved_playlists()
    selected = next(
        (
            item for item in items
            if item["id"] == playlist_id
            and (_is_admin() or str(item.get("owner", "")).strip() == _current_username())
        ),
        None,
    )
    if not selected:
        return jsonify({"error": "Not Found", "details": "Saved playlist not found"}), 404
    return jsonify(selected)


@api_bp.route("/playlist/<playlist_id>/m3u", methods=["GET"])
def generate_saved_playlist(playlist_id):
    """Generate an M3U playlist from a saved preset using a short URL."""
    items = load_saved_playlists()
    selected = next((item for item in items if item["id"] == playlist_id), None)
    if not selected:
        return jsonify({"error": "Not Found", "details": "Saved playlist not found"}), 404

    m3u_playlist, filename, error_json, error_code = build_playlist_from_config(selected.get("config", {}))
    if error_json:
        return jsonify(error_json), error_code

    preview_mode = request.args.get("preview", "").lower() in {"1", "true", "yes", "on"}
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    if preview_mode:
        return Response(m3u_playlist, mimetype="text/plain", headers=headers)

    headers["Content-Disposition"] = f"attachment; filename={filename}"
    return Response(m3u_playlist, mimetype="audio/x-scpls", headers=headers)


@api_bp.route("/playlist/<playlist_id>/xmltv", methods=["GET"])
def generate_saved_xmltv(playlist_id):
    """Generate an XMLTV from a saved preset using a short URL."""
    items = load_saved_playlists()
    selected = next((item for item in items if item["id"] == playlist_id), None)
    if not selected:
        return jsonify({"error": "Not Found", "details": "Saved playlist not found"}), 404

    config = selected.get("config", {})
    xmltv_data, error_json, error_code = build_xmltv_from_config(config)
    if error_json:
        return jsonify(error_json), error_code

    preview_mode = request.args.get("preview", "").lower() in {"1", "true", "yes", "on"}
    headers = {}
    if not preview_mode:
        headers["Content-Disposition"] = "attachment; filename=guide.xml"

    return Response(xmltv_data, mimetype="application/xml", headers=headers)


@api_bp.route("/categories", methods=["GET"])
def get_categories():
    """Get all available categories from the Xtream API"""
    # Get and validate parameters
    url, username, password, _proxy_url, error, status_code = get_required_params()
    if error:
        return error, status_code

    # Check for VOD parameter - default to false to avoid timeouts (VOD is massive and slow!)
    include_vod = request.args.get("include_vod", "false").lower() == "true"
    logger.info(f"VOD content requested: {include_vod}")

    # Validate credentials
    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Fetch categories
    categories, channels, error_json, error_code = fetch_categories_and_channels(
        url,
        username,
        password,
        include_vod,
        include_all_streams=True,
    )
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Return categories plus stream metadata for channel-level filtering UI.
    return jsonify({"categories": categories, "streams": channels})


@api_bp.route("/stream-link", methods=["GET"])
def get_stream_link():
    """Build direct stream link for viewer playback."""
    url, username, password, _proxy_url, error, status_code = get_required_params()
    if error:
        return error, status_code

    stream_id = request.args.get("stream_id")
    content_type = request.args.get("content_type", "live")
    extension = request.args.get("extension", "ts")
    timeshift_start = request.args.get("timeshift_start")
    timeshift_duration = request.args.get("timeshift_duration")

    if not stream_id:
        return jsonify({"error": "Missing Parameters", "details": "Required: stream_id"}), 400

    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    candidates = build_stream_link_candidates(
        server_info=user_data.get("server_info"),
        username=username,
        password=password,
        content_type=content_type,
        stream_id=stream_id,
        extension=extension,
        timeshift={"start": timeshift_start, "duration": timeshift_duration},
    )
    upstream_link = candidates[0] if candidates else build_stream_link(
        server_info=user_data.get("server_info"),
        username=username,
        password=password,
        content_type=content_type,
        stream_id=stream_id,
        extension=extension,
        timeshift={"start": timeshift_start, "duration": timeshift_duration},
    )
    if not candidates and upstream_link:
        candidates = [upstream_link]
    proxy_base = request.host_url.rstrip("/")
    proxy_candidates = [f"{proxy_base}/stream-proxy/{encode_url(link)}" for link in candidates if link]
    link = proxy_candidates[0] if proxy_candidates else ""

    return jsonify(
        {
            "url": link,
            "candidates": proxy_candidates,
            "content_type": content_type,
            "stream_id": stream_id,
            "extension": extension,
            "timeshift": {
                "start": timeshift_start,
                "duration": timeshift_duration,
            },
        }
    )


@api_bp.route("/xmltv", methods=["GET"])
def generate_xmltv():
    """Generate a filtered XMLTV file from the Xtream API"""
    # Get and validate parameters
    url, username, password, proxy_url, error, status_code = get_required_params()
    if error:
        return error, status_code

    wanted_groups = parse_group_list(request.args.get("wanted_groups", ""))
    unwanted_groups = parse_group_list(request.args.get("unwanted_groups", ""))
    wanted_stream_ids = parse_stream_id_list(request.args.get("wanted_stream_ids", ""))
    unwanted_stream_ids = parse_stream_id_list(request.args.get("unwanted_stream_ids", ""))

    # Validate credentials
    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    xmltv_data, error_json, error_code = build_xmltv_from_config(
        {
            "url": url,
            "username": username,
            "password": password,
            "wanted_groups": ",".join(wanted_groups) if wanted_groups else "",
            "unwanted_groups": ",".join(unwanted_groups) if unwanted_groups else "",
            "wanted_stream_ids": ",".join(wanted_stream_ids) if wanted_stream_ids else "",
            "unwanted_stream_ids": ",".join(unwanted_stream_ids) if unwanted_stream_ids else "",
        }
    )
    if error_json:
        return json.dumps(error_json), error_code, {"Content-Type": "application/json"}

    # Return the XMLTV data
    return Response(
        xmltv_data, mimetype="application/xml", headers={"Content-Disposition": "attachment; filename=guide.xml"}
    )


@api_bp.route("/m3u", methods=["GET", "POST"])
def generate_m3u():
    """Generate a filtered M3U playlist from the Xtream API"""
    # Get and validate parameters
    url, username, password, proxy_url, error, status_code = get_required_params()
    if error:
        return error, status_code

    # Parse filter parameters (support both GET and POST for large filter lists)
    if request.method == "POST":
        data = request.get_json() or {}
        unwanted_groups = parse_group_list(data.get("unwanted_groups", ""))
        wanted_groups = parse_group_list(data.get("wanted_groups", ""))
        unwanted_stream_ids = parse_stream_id_list(data.get("unwanted_stream_ids", ""))
        wanted_stream_ids = parse_stream_id_list(data.get("wanted_stream_ids", ""))
        no_stream_proxy = False
        include_vod = str(data.get("include_vod", "false")).lower() == "true"
        include_channel_id = str(data.get("include_channel_id", "false")).lower() == "true"
        channel_id_tag = str(data.get("channel_id_tag", "channel-id"))
        logger.info("🔄 Processing POST request for M3U generation")
    else:
        unwanted_groups = parse_group_list(request.args.get("unwanted_groups", ""))
        wanted_groups = parse_group_list(request.args.get("wanted_groups", ""))
        unwanted_stream_ids = parse_stream_id_list(request.args.get("unwanted_stream_ids", ""))
        wanted_stream_ids = parse_stream_id_list(request.args.get("wanted_stream_ids", ""))
        no_stream_proxy = False
        include_vod = request.args.get("include_vod", "false").lower() == "true"
        include_channel_id = request.args.get("include_channel_id", "false") == "true"
        channel_id_tag = request.args.get("channel_id_tag", "channel-id")
        logger.info("🔄 Processing GET request for M3U generation")

    # For M3U generation, warn about VOD performance impact
    if include_vod:
        logger.warning("⚠️  M3U generation with VOD enabled - expect 2-5 minute generation time!")
    else:
        logger.info("⚡ M3U generation for live content only - should be fast!")

    # Log filter parameters (truncate if too long for readability)
    wanted_display = f"{len(wanted_groups)} groups" if len(wanted_groups) > 10 else str(wanted_groups)
    unwanted_display = f"{len(unwanted_groups)} groups" if len(unwanted_groups) > 10 else str(unwanted_groups)
    wanted_stream_display = f"{len(wanted_stream_ids)} streams"
    unwanted_stream_display = f"{len(unwanted_stream_ids)} streams"
    logger.info(
        "Filter parameters - wanted_groups: %s, unwanted_groups: %s, wanted_stream_ids: %s, unwanted_stream_ids: %s, include_vod: %s",
        wanted_display,
        unwanted_display,
        wanted_stream_display,
        unwanted_stream_display,
        include_vod,
    )

    # Warn about massive filter lists
    total_filters = len(wanted_groups) + len(unwanted_groups) + len(wanted_stream_ids) + len(unwanted_stream_ids)
    if total_filters > 20:
        logger.warning(f"⚠️  Large filter list detected ({total_filters} categories) - this will be slower!")
    if total_filters > 50:
        logger.warning(f"🐌 MASSIVE filter list ({total_filters} categories) - expect 3-5 minute processing time!")

    # Validate credentials
    user_data, error_json, error_code = validate_xtream_credentials(url, username, password)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Fetch categories and channels
    categories, streams, error_json, error_code = fetch_categories_and_channels(url, username, password, include_vod)
    if error_json:
        return error_json, error_code, {"Content-Type": "application/json"}

    # Extract user info and server URL
    username = user_data["user_info"]["username"]
    password = user_data["user_info"]["password"]

    server_url = f"http://{user_data['server_info']['url']}:{user_data['server_info']['port']}"

    # Generate M3U playlist
    m3u_playlist = generate_m3u_playlist(
        url=url,
        username=username,
        password=password,
        server_url=server_url,
        categories=categories,
        streams=streams,
        wanted_groups=wanted_groups,
        unwanted_groups=unwanted_groups,
        wanted_stream_ids=wanted_stream_ids,
        unwanted_stream_ids=unwanted_stream_ids,
        no_stream_proxy=no_stream_proxy,
        include_vod=include_vod,
        include_channel_id=include_channel_id,
        channel_id_tag=channel_id_tag,
        proxy_url=proxy_url
    )

    # Determine filename based on content included
    filename = "FullPlaylist.m3u" if include_vod else "LiveStream.m3u"

    # Return the M3U playlist with proper CORS headers for frontend
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

    return Response(m3u_playlist, mimetype="audio/x-scpls", headers=headers)
