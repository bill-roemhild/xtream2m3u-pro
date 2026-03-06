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

`GET /auth/status`

- Auth: none
- Required: none
- Returns setup/login state (`needs_setup`, `authenticated`, `username`, `is_admin`, `user_count`)

`POST /auth/setup`

- Auth: none (first-run only)
- Required JSON: `username`, `password` (`password` min length 8)
- Creates the initial admin account and starts an authenticated session

`POST /auth/login`

- Auth: none
- Required JSON: `username`, `password`
- Returns 429 with `retry_after` when temporary lockout is active

`POST /auth/logout`

- Auth: logged-in user
- Required: none
- Clears session

`GET /auth/users`

- Auth: admin
- Required: none
- Lists users (without password hashes)

`POST /auth/users`

- Auth: admin
- Required JSON: `username`, `password`
- Optional JSON: `is_admin` (bool)

`POST /auth/users/delete`

- Auth: admin
- Required JSON: `username`
- Deletes user plus their owned profiles/playlists
- Cannot delete your own account or the last admin

### Backup and Restore

`GET /backup/download`

- Auth: admin
- Required: none
- Downloads JSON backup containing `auth_users`, `profiles`, `saved_playlists`

`POST /backup/restore`

- Auth: admin
- Required multipart form-data: `file` (JSON backup file)
- Overwrites all stores with backup content
- Response includes `relogin_required` if current session user no longer exists

### Service Profiles

`GET /profiles`

- Auth: logged-in user
- Required: none
- Admin sees all profiles; non-admin sees only owned profiles

`POST /profiles`

- Auth: logged-in user
- Required JSON: `name`, `url`, `username`, `password`
- Optional JSON: `include_vod`, `owner` (admin can set owner)
- Creates or updates profile by `(owner, name)`

`POST /profiles/delete`

- Auth: logged-in user
- Required JSON: `name`
- Optional JSON: `owner` (admin targeted delete)

### Saved Playlist Presets

`GET /saved-playlists`

- Auth: logged-in user
- Required: none
- Optional query: `url`, `username`, `owner`
- Admin filtering supports `owner`; non-admin sees only owned presets

`POST /saved-playlists`

- Auth: logged-in user
- Required JSON: `name`, `url`, `username`, `password`
- Optional JSON: `id` (update existing), `owner` (admin), `wanted_groups`, `unwanted_groups`, `wanted_stream_ids`, `unwanted_stream_ids`, `include_vod`, `include_channel_id`, `channel_id_tag`
- Returns short M3U/XMLTV URLs for the saved preset

`GET /saved-playlists/<id>`

- Auth: logged-in user
- Required path: `id`
- Admin can fetch any; non-admin only own preset

`POST /saved-playlists/delete`

- Auth: logged-in user
- Required JSON: `id`
- Admin can delete any; non-admin only own preset

### Generated Output Endpoints

`GET|POST /m3u`

- Auth: none (public endpoint)
- Required params (query for GET, JSON for POST): `url`, `username`, `password`
- Optional filters: `wanted_groups`, `unwanted_groups`, `wanted_stream_ids`, `unwanted_stream_ids`
- Optional options: `include_vod`, `include_channel_id`, `channel_id_tag`

`GET /xmltv`

- Auth: none (public endpoint)
- Required query: `url`, `username`, `password`
- Optional filters: `wanted_groups`, `unwanted_groups`, `wanted_stream_ids`, `unwanted_stream_ids`

`GET /playlist/<id>/m3u`

- Auth: none (public endpoint)
- Required path: `id`
- Optional query: `preview=true|1|yes|on` (returns plain text preview instead of attachment)

`GET /playlist/<id>/xmltv`

- Auth: none (public endpoint)
- Required path: `id`
- Optional query: `preview=true|1|yes|on` (returns inline XML instead of attachment)

### Service Data and Viewer Support

`GET /subscription`

- Auth: logged-in user
- Required query: `url`, `username`, `password`
- Returns normalized subscription and server details

`GET /categories`

- Auth: logged-in user
- Required query: `url`, `username`, `password`
- Optional query: `include_vod=true|false`
- Returns `categories` plus `streams`

`GET /stream-link`

- Auth: logged-in user
- Required query: `url`, `username`, `password`, `stream_id`
- Optional query: `content_type` (`live` default), `extension` (`ts` default), `timeshift_start`, `timeshift_duration`
- Returns proxy URL candidates for viewer playback

`GET /stream-proxy/<encoded-upstream-url>`

- Auth: none (public endpoint)
- Required path: URL-encoded upstream media URL
- Proxies TS/HLS; rewrites HLS manifests so segment/key requests continue through app proxy

`GET /image-proxy/<encoded-image-url>`

- Auth: none (public endpoint)
- Required path: URL-encoded image URL
- Proxies images for logo/CORS compatibility

`GET /version`

- Auth: none
- Required: none
- Returns current runtime app version

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
