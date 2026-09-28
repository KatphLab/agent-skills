---
name: zoho-workdrive-download
description: Download files from Zoho WorkDrive using a share link or file ID. Use when the user provides a WorkDrive URL like https://workdrive.zoho.in/file/... or https://workdrive.zoho.com/file/..., wants to download a document from Zoho WorkDrive, or mentions pulling files from WorkDrive.
disable-model-invocation: true
---

# Zoho WorkDrive Downloader

Download files from Zoho WorkDrive given a share link or file ID.

## Quick Start

> **IMPORTANT**: Always invoke the script with `python` (the system Python). Do NOT use `python3`, `python2`, or any versioned alias — those may resolve to a different interpreter than the system default and cause import/version mismatches. Use exactly `python`.

```bash
python <SKILL_DIR>/scripts/download.py "<workdrive_url>" --output <destination>
```

`<SKILL_DIR>` = the directory containing this SKILL.md.

## Input Formats

The script accepts any of these:

- **Full URL**: `https://workdrive.zoho.in/file/527ax3d8cbaf6211945eaaecee2724cae4040`
- **Other regional domains**: `workdrive.zoho.com`, `workdrive.zoho.eu`, `workdrive.zoho.com.au`, `workdrive.zoho.jp`
- **Bare file ID**: `527ax3d8cbaf6211945eaaecee2724cae4040`

## Authentication

The script handles the full OAuth2 token lifecycle automatically. You provide credentials once; tokens are managed and cached in the config file.

### Config file (`~/.zoho-workdrive.json`)

Initial setup — you provide `client_id`, `client_secret`, and a one-time `code`:

```json
{
  "client_id": "1000.XXXXXXXXXX",
  "client_secret": "abcdef1234567890",
  "code": "1000.abc123.xyz789"
}
```

After the first run, the script adds `access_token`, `refresh_token`, `token_expiry`, and `accounts_url` to the same file:

```json
{
  "client_id": "1000.XXXXXXXXXX",
  "client_secret": "abcdef1234567890",
  "access_token": "1000.xxx...",
  "refresh_token": "1000.yyy...",
  "token_expiry": 1750000000,
  "accounts_url": "https://accounts.zoho.in"
}
```

### Token lifecycle

The script resolves a valid token in this order:

1. **Cached access_token** exists and not expired → use silently (no network call, no output)
2. **Expired** → use `refresh_token` to get a new one automatically
3. **Refresh fails** → exchange `code` from config for new tokens
4. **Nothing available** → error with instructions

Access tokens are **never printed** — only used in API calls.

### Getting a one-time auth code

1. Go to [Zoho API Console](https://api-console.zoho.com/)
2. Create a **Self Client** or **Server-based Application**
3. Click **"Generate Code"** → scopes: `WorkDrive.files.READ, ZohoFiles.files.READ`
4. Paste the code into `~/.zoho-workdrive.json` as `"code"`

## Examples

> **All examples use `python`, never `python3` or `python2`.**

```bash
# Download using full URL
python scripts/download.py "https://workdrive.zoho.in/file/527ax3d8cbaf6211945eaaecee2724cae4040"

# Download to a specific directory
python scripts/download.py "https://workdrive.zoho.in/file/527ax3d8cbaf6211945eaaecee2724cae4040" --output ./downloads/

# Use a custom config file
python scripts/download.py "https://workdrive.zoho.in/file/abc123" --config ~/my-zoho-config.json

# Use a different regional domain
python scripts/download.py "https://workdrive.zoho.com/file/abc123" --base-url https://workdrive.zoho.com/api/v1
```

## Options

| Flag             | Description                                                  |
| ---------------- | ------------------------------------------------------------ |
| `--output`, `-o` | Output file path or directory (default: current directory)   |
| `--config`, `-c` | Path to config JSON file (default: `~/.zoho-workdrive.json`) |
| `--base-url`     | Override API base URL                                        |

## How It Works

1. Extracts the file ID from the URL (the segment after `/file/`)
2. Auto-detects the correct regional API endpoint (`.in`, `.com`, `.eu`, etc.)
3. Fetches file metadata (name, size) for display
4. Downloads the file via `GET /api/v1/files/{id}/download`
5. Saves with the original filename

## Dependencies

- Python 3.8+
- `requests` library (`pip install requests`)

## Troubleshooting

| Issue                   | Fix                                                                       |
| ----------------------- | ------------------------------------------------------------------------- |
| `Config file not found` | Create `~/.zoho-workdrive.json` with `client_id`, `client_secret`, `code` |
| `No valid credentials`  | Generate a new auth code from Zoho API Console and add to config          |
| `Auth code expired`     | The code is one-time and short-lived — generate a new one                 |
| `Refresh token invalid` | Delete `refresh_token` from config, add a new `code`, run again           |
| `File not found`        | Check the URL; file may be deleted or access revoked                      |
| Wrong region            | Use `--base-url` to override, or check the URL domain                     |
