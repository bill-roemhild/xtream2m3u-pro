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
6. Click **Create Playlist**, choose channel groups/channels, enter a playlist name, then click **Save Playlist**.
7. In **Saved Playlists For Selected Service**, copy:
   - M3U link (playlist URL)
   - EPG/XMLTV link
8. Open your M3U-enabled app/player and add a new playlist/provider using URL mode.
9. Paste the copied M3U link as the playlist source.
10. Paste the copied EPG/XMLTV link in the app’s EPG/TV Guide source field.
11. Save/refresh in your player so channels and guide data load.

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

- `FORCE_SSL_REMOTE` (default: `true`; redirects non-local HTTP requests to HTTPS)
- `TRUST_PROXY_HEADERS` (default: `true`; enables `ProxyFix` so `X-Forwarded-*` headers are honored behind reverse proxies)
- `SSL_CERT_FILE` (default: `/data/tls/tls.crt`; certificate path for native HTTPS listener)
- `SSL_KEY_FILE` (default: `/data/tls/tls.key`; private key path for native HTTPS listener)
- `SSL_CERT_SUBJECT` (optional; subject used when auto-generating self-signed cert, default `/CN=xtream2m3u.local`)

Versioning:

- `APP_VERSION_FILE` (default: `/app/VERSION`)
- `GET /version` returns the current app version for UI display.

## API Summary

Authentication:

- `GET /auth/status`
- `POST /auth/setup`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/users` (admin)
- `POST /auth/users` (admin)
- `POST /auth/users/delete` (admin)

Backup/restore (admin):

- `GET /backup/download`
- `POST /backup/restore`

Profiles:

- `GET /profiles`
- `POST /profiles`
- `POST /profiles/delete`

Playlist presets:

- `GET /saved-playlists`
- `POST /saved-playlists`
- `GET /saved-playlists/<id>`
- `POST /saved-playlists/delete`

Generated outputs:

- `GET|POST /m3u`
- `GET /xmltv`
- `GET /playlist/<id>/m3u`
- `GET /playlist/<id>/xmltv`

Service data:

- `GET /categories`
- `GET /subscription`
- `GET /stream-link` (used by channel viewer playback)

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
