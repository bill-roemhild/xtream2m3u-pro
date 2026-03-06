# xtream2m3u-pro

> Thanks to the original project at https://github.com/ovosimpatico/xtream2m3u for the base code.

Web UI and API for building filtered M3U/XMLTV outputs from Xtream-compatible IPTV services.

## Overview

This project lets users:

- Save multiple Xtream service profiles (URL/username/password).
- Connect to a service and load categories/channels.
- Build filtered playlists at category and channel level.
- Save reusable playlist definitions and use short URLs:
  - `/playlist/<id>/m3u`
  - `/playlist/<id>/xmltv`
- Preview generated M3U/XMLTV content from the UI.
- Use built-in user authentication and multi-user ownership rules.

## Key Features

- Multi-user login system with first-run admin setup.
- Admin/user separation:
  - Users only see their own services and playlists.
  - Admin can manage all users, services, and playlists.
- Service profile management (create/edit/delete).
- Playlist builder with channel-group + per-channel filtering.
- Saved playlists scoped to selected service in the UI.
- Backup/restore (admin): users, services, and playlists.
- Channel viewer modal with m3u8/ts playback attempts.
- Login rate limiting with temporary lockouts.
- Encrypted storage for upstream Xtream credentials at rest.

## Security Notes

- Password hashes for app users are stored with Werkzeug password hashing.
- Upstream Xtream credentials in profile/playlist stores are encrypted with Fernet before writing to disk.
- Login endpoint includes temporary lockouts after repeated failures.

Defaults:

- `AUTH_MAX_LOGIN_ATTEMPTS=5`
- `AUTH_ATTEMPT_WINDOW_SECONDS=300`
- `AUTH_LOCKOUT_SECONDS=300`

## Requirements

- Docker + Docker Compose (recommended), or
- Python 3.10+

## Docker Quick Start

```bash
docker compose up -d --build
```

If you are starting from scratch locally, set up the repo first:

```bash
git clone https://github.com/bill-roemhild/xtream2m3u-pro.git
cd xtream2m3u-pro
git checkout development
git pull origin development
```

With the provided compose file:

- Container listens on `5000`
- Host mapping is `5000:5000`
- UI URL: `https://localhost:5000`
- On first startup, the container auto-generates a self-signed certificate under `/data/tls`.
- Browsers will show a certificate warning unless you install/trust your own cert.

Data is persisted in a Docker volume (`xtream2m3u_data`) mounted at `/data`.

## Native Run

```bash
pip install -r requirements.txt
python run.py --port 5000
```

Then open `http://localhost:5000` (native run is dev HTTP unless you run Gunicorn with cert/key flags).

## First-Run Flow

1. Open the UI.
2. If no users exist, create the initial admin account.
3. Log in.
4. Add at least one service profile.
5. Click **Connect** to load categories.
6. Create and save playlists.

## Environment Variables

Core:

- `CREDENTIAL_PROFILE_STORE` (default: `/data/credential_profiles.json`)
- `PLAYLIST_STORE_PATH` (default: `/data/saved_playlists.json`)
- `AUTH_STORE_PATH` (default: `/data/auth_users.json`)
- `AUTH_THROTTLE_STORE_PATH` (default: `/data/auth_login_throttle.json`)

Session / app:

- `FLASK_SECRET_KEY` (optional fixed key)
- `SECRET_KEY` (alternate name)
- `FLASK_SECRET_FILE` (default: `/data/flask_secret_key`)

Credential encryption:

- `CREDENTIAL_CIPHER_KEY` (optional Fernet key; if unset, generated/persisted)
- `CREDENTIAL_CIPHER_FILE` (default: `/data/credential_cipher_key`)

Login lockout tuning:

- `AUTH_MAX_LOGIN_ATTEMPTS` (default: `5`)
- `AUTH_ATTEMPT_WINDOW_SECONDS` (default: `300`)
- `AUTH_LOCKOUT_SECONDS` (default: `300`)

Optional:

- `PROXY_URL` (legacy/default proxy base value; current playlist generation is configured for direct stream URLs)
- `FORCE_SSL_REMOTE` (default: `true`; redirects non-local HTTP requests to HTTPS)
- `TRUST_PROXY_HEADERS` (default: `true`; enables `ProxyFix` so `X-Forwarded-*` headers are honored behind reverse proxies)
- `SSL_CERT_FILE` (default: `/data/tls/tls.crt`; certificate path for native HTTPS listener)
- `SSL_KEY_FILE` (default: `/data/tls/tls.key`; private key path for native HTTPS listener)
- `SSL_CERT_SUBJECT` (optional; subject used when auto-generating self-signed cert, default `/CN=xtream2m3u.local`)

Versioning:

- `APP_VERSION` (optional override for displayed/runtime version)
- `APP_VERSION_FILE` (default: `/app/VERSION`)
- `GET /version` returns the current app version for UI display.
- GitHub Actions Docker builds inject `APP_VERSION` from workflow metadata (tag/sha based).

## API Reference (Required Inputs)

Base URL examples:

- `https://localhost:5000` (local Docker default)
- `https://<server>:5000`

Auth model:

- Session/cookie auth is required for most API routes.
- Public routes (no login required): `GET /auth/status`, `POST /auth/setup`, `POST /auth/login`, `GET|POST /m3u`, `GET /xmltv`, `GET /playlist/<id>/m3u`, `GET /playlist/<id>/xmltv`, `GET /version`, `GET /stream-proxy/<...>`, `GET /image-proxy/<...>`.

### Auth and User Management

`GET /auth/status` (public)

```json
{
  "needs_setup": false,
  "authenticated": true,
  "username": "admin",
  "is_admin": true,
  "user_count": 2
}
```

`POST /auth/setup` (public, first-run only)

```json
{
  "username": "admin",
  "password": "password123"
}
```

`POST /auth/login` (public)

```json
{
  "username": "admin",
  "password": "password123"
}
```

`POST /auth/logout` (login required, no request body)

`GET /auth/users` (admin)

```json
{
  "users": [
    {
      "username": "admin",
      "is_admin": true,
      "created_at": 1772774362
    }
  ]
}
```

`POST /auth/users` (admin)

```json
{
  "username": "james",
  "password": "password123",
  "is_admin": false
}
```

`POST /auth/users/delete` (admin)

```json
{
  "username": "james"
}
```

### Backup and Restore

`GET /backup/download` (admin)

```json
{
  "version": 1,
  "generated_at": 1772774362,
  "auth_users": [],
  "profiles": [],
  "saved_playlists": []
}
```

`POST /backup/restore` (admin, multipart form-data)

- required form field: `file` (backup JSON)

```json
{
  "ok": true,
  "restored": {
    "users": 2,
    "profiles": 4,
    "saved_playlists": 8
  },
  "relogin_required": false
}
```

### Service Profiles

`GET /profiles` (login required)

```json
{
  "profiles": [
    {
      "name": "Prime",
      "url": "http://provider:826",
      "username": "consumer420",
      "password": "secret",
      "include_vod": false,
      "owner": "admin"
    }
  ],
  "store_path": "/data/credential_profiles.json"
}
```

`POST /profiles` (login required)

```json
{
  "name": "Prime",
  "url": "http://provider:826",
  "username": "consumer420",
  "password": "secret",
  "include_vod": false,
  "owner": "admin"
}
```

`POST /profiles/delete` (login required)

```json
{
  "name": "Prime",
  "owner": "admin"
}
```

### Saved Playlist Presets

`GET /saved-playlists` (login required)

- optional query: `url`, `username`, `owner` (owner filter works for admin)

```json
{
  "items": [
    {
      "id": "60483f9fa4ff",
      "name": "News Only",
      "owner": "admin",
      "created_at": 1772774362,
      "url": "https://host/playlist/60483f9fa4ff/m3u",
      "m3u_url": "https://host/playlist/60483f9fa4ff/m3u",
      "xmltv_url": "https://host/playlist/60483f9fa4ff/xmltv"
    }
  ],
  "store_path": "/data/saved_playlists.json"
}
```

`POST /saved-playlists` (login required)

```json
{
  "id": "60483f9fa4ff",
  "name": "News Only",
  "url": "http://provider:826",
  "username": "consumer420",
  "password": "secret",
  "owner": "admin",
  "wanted_groups": "News,Sports",
  "unwanted_groups": "",
  "wanted_stream_ids": "10,12",
  "unwanted_stream_ids": "",
  "include_vod": false,
  "include_channel_id": false,
  "channel_id_tag": "channel-id"
}
```

`GET /saved-playlists/<id>` (login required, owner-scoped for non-admin)

```json
{
  "id": "60483f9fa4ff",
  "name": "News Only",
  "created_at": 1772774362,
  "owner": "admin",
  "config": {
    "url": "http://provider:826",
    "username": "consumer420",
    "password": "secret"
  }
}
```

`POST /saved-playlists/delete` (login required)

```json
{
  "id": "60483f9fa4ff"
}
```

### Generated Output Endpoints

`GET|POST /m3u` (public)

- required inputs: `url`, `username`, `password`
- optional inputs: `wanted_groups`, `unwanted_groups`, `wanted_stream_ids`, `unwanted_stream_ids`, `include_vod`, `include_channel_id`, `channel_id_tag`

POST JSON example:

```json
{
  "url": "http://provider:826",
  "username": "consumer420",
  "password": "secret",
  "wanted_groups": "News,Sports",
  "wanted_stream_ids": "10,12",
  "include_vod": false
}
```

`GET /xmltv` (public)

- required query: `url`, `username`, `password`
- optional query: `wanted_groups`, `unwanted_groups`, `wanted_stream_ids`, `unwanted_stream_ids`

`GET /playlist/<id>/m3u` (public)

- optional query: `preview=true|1|yes|on`

`GET /playlist/<id>/xmltv` (public)

- optional query: `preview=true|1|yes|on`

### Service Data and Viewer Support

`GET /subscription` (login required)

- required query: `url`, `username`, `password`

```json
{
  "status": "Active",
  "profile": {
    "username": "consumer420",
    "max_connections": 5
  },
  "server": {
    "url": "provider.host",
    "port": 826
  }
}
```

`GET /categories` (login required)

- required query: `url`, `username`, `password`
- optional query: `include_vod=true|false`

```json
{
  "categories": [],
  "streams": []
}
```

`GET /stream-link` (login required)

- required query: `url`, `username`, `password`, `stream_id`
- optional query: `content_type`, `extension`, `timeshift_start`, `timeshift_duration`

```json
{
  "url": "https://host/stream-proxy/http%3A%2F%2Fprovider%2Flive%2Fu%2Fp%2F72.ts",
  "candidates": [
    "https://host/stream-proxy/http%3A%2F%2Fprovider%2Flive%2Fu%2Fp%2F72.ts"
  ],
  "content_type": "live",
  "stream_id": "72",
  "extension": "ts",
  "timeshift": {
    "start": null,
    "duration": null
  }
}
```

`GET /stream-proxy/<encoded-upstream-url>` (public)

- required path: URL-encoded upstream media URL

`GET /image-proxy/<encoded-image-url>` (public)

- required path: URL-encoded image URL

`GET /version` (public)

```json
{
  "version": "0.2.5"
}
```

## Backup / Restore Behavior

- Backup exports users, profiles, and playlists.
- Restoring backup overwrites current stores.
- If the current logged-in user no longer exists after restore, session is cleared and re-login is required.
- Backup exports upstream service credentials in plaintext so backups can be restored across instances with different cipher keys.
- Restored upstream credentials are always re-encrypted at rest in the local stores.

## Notes on IDs and URLs

- Saved playlist IDs are generated as 12-char hex IDs.
- Short playlist URLs are returned by `/saved-playlists` and `/saved-playlists (POST)`.
- UI supports copy and view actions for both M3U and XMLTV outputs.

## Development

Run syntax check:

```bash
python -m compileall app
```

## License

This project is licensed under AGPLv3. See `LICENSE`.

## Disclaimer

This software does not provide IPTV content. Use only with subscriptions and content you are authorized to access.
