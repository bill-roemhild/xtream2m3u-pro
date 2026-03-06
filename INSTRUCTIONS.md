# xtream2m3u-pro Instructions

This guide walks through the full flow to create a playlist, starting from adding a server.

## 1. Open the App

1. Open the web UI (example: `https://localhost:5000`).
2. Log in.
3. If this is first run, create the initial admin account first.

## 2. Add a Server Profile

1. In **Service Credentials** (Step 1), click **New**.
2. In **Add New Server**, enter:
   - **Profile Name**
   - **Service URL** (example: `http://provider-host:port`)
   - **Username**
   - **Password**
   - Optional: **Include VOD Content**
3. Click **Save**.
4. Confirm the new profile appears in **Saved Servers** dropdown.
5. Select that profile if it is not already selected.

## 3. Connect and Load Categories

1. Click **Connect**.
2. Wait for categories/channels to load.
3. Verify Step 2 opens and shows:
   - **Saved Playlists For Selected Service**
   - **Create Playlist** button
   - Subscription details (if available from provider)

## 4. Create a Playlist

1. Click **Create Playlist**.
2. In the modal:
   - Enter **Playlist Name** (required).
   - Choose filter mode:
     - **Include Selected** (most common)
     - **Exclude Selected**
3. Select content:
   - Use category groups.
   - Click **Edit Channels** under a group for per-channel control.
   - In channel editor:
     - check/uncheck channels
     - optional: click **View** to preview a channel stream
     - click **Done** when finished
4. Back in playlist modal, verify selection counts.
5. Click **Save Playlist**.

## 5. Use Playlist URLs

For each saved playlist entry, use:

- **M3U URL**: `http(s)://<host>/playlist/<id>/m3u`
- **XMLTV URL**: `http(s)://<host>/playlist/<id>/xmltv`

If you use the provided Docker Compose setup, use `https://<host>:5000/...`.

Available actions in list:

- **Copy M3U URL**
- **View M3U Content**
- **Copy XMLTV URL**
- **View XMLTV Content**

## 6. Edit an Existing Playlist

1. In saved playlists list, click **Edit** (pencil icon).
2. Playlist modal opens with existing selections loaded.
3. Update playlist name and/or channel selections.
4. Click **Update Playlist**.

## 7. Delete an Existing Playlist

1. In saved playlists list, click **Delete** (trash icon).
2. Confirm in the delete modal.

## 8. Server Profile Maintenance

- **Edit server**: select profile, click **Edit**, update fields, then **Save**.
- **Delete server**: select profile, click **Delete**, confirm.

## 9. Multi-User Notes

- Regular users only see their own services/playlists.
- Admin can see and manage all users' records.
- Admin can use **User Maintenance** for user create/delete.

## 10. Backup and Restore (Admin)

1. Click **Backup / Restore**.
2. To backup: click **Download Backup**.
3. To restore:
   - choose backup JSON file
   - click **Restore Backup**
4. If current user no longer exists in restored data, re-login is required.

## Troubleshooting

- **"Setup a server first."**
  - Create a server profile in Step 1 before clicking Connect.

- **No categories load**
  - Re-check URL/username/password.
  - Confirm provider API endpoint is reachable from server.

- **Playlist not showing in list**
  - Ensure you are on the same selected service profile used when saving.

- **Viewer stream does not play**
  - Some providers block browser playback/CORS or stream formats.
  - Test both m3u8/ts channels from your provider.
