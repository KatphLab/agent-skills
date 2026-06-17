#!/usr/bin/env python3
"""
Zoho WorkDrive File Downloader
Downloads files from Zoho WorkDrive using the API with full OAuth2 lifecycle.

Config file (~/.zoho-workdrive.json):
    Required: client_id, client_secret, code (one-time auth code)
    Auto-managed: access_token, refresh_token, token_expiry, accounts_url

    The script writes generated tokens back to the config for reuse.
    Access tokens are never printed — only used in API calls.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("Error: 'requests' library required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = Path("~/.zoho-workdrive.json").expanduser()

ACCOUNTS_URLS = {
    "zoho.in":    "https://accounts.zoho.in",
    "zoho.com":   "https://accounts.zoho.com",
    "zoho.eu":    "https://accounts.zoho.eu",
    "zoho.com.au": "https://accounts.zoho.com.au",
    "zoho.jp":    "https://accounts.zoho.jp",
}


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        _die(
            f"Config file not found: {config_path}\n"
            "Create it with your Zoho app credentials:\n"
            '  {"client_id": "...", "client_secret": "...", "code": "..."}\n'
            "See https://api-console.zoho.com/ to create an app."
        )
    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        _die(f"Cannot read config {config_path}: {e}")
    return cfg


def save_config(config_path: Path, cfg: dict) -> None:
    tmp = config_path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    tmp.replace(config_path)


def _die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Accounts URL detection
# ---------------------------------------------------------------------------

def detect_accounts_url(workdrive_url: str | None, cfg: dict) -> str:
    if cfg.get("accounts_url"):
        return cfg["accounts_url"].rstrip("/")

    if workdrive_url:
        host = urlparse(workdrive_url).hostname or ""
        for domain, url in ACCOUNTS_URLS.items():
            if domain in host:
                return url

    return "https://accounts.zoho.in"


# ---------------------------------------------------------------------------
# Token exchange — auth code → access_token + refresh_token
# ---------------------------------------------------------------------------

def exchange_auth_code(accounts_url: str, cfg: dict, config_path: Path) -> str:
    client_id = cfg.get("client_id")
    client_secret = cfg.get("client_secret")
    code = cfg.get("code")

    if not client_id or not client_secret:
        _die("client_id and client_secret are required in the config file.")
    if not code:
        _die(
            "No 'code' (auth code) in config.\n"
            "Generate one from https://api-console.zoho.com/:\n"
            "  1. Go to your app → 'Generate Code'\n"
            "  2. Scopes: WorkDrive.files.READ, ZohoFiles.files.READ\n"
            "  3. Paste the code into ~/.zoho-workdrive.json as \"code\""
        )

    print("Exchanging auth code for tokens...")
    resp = requests.post(f"{accounts_url}/oauth/v2/token", data={
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }, timeout=30)

    data = resp.json()
    if "error" in data:
        _die(
            f"Auth code exchange failed: {data.get('error_description', data['error'])}\n"
            "The code may be expired or already used. Generate a new one."
        )

    access_token = data["access_token"]
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in", 3600)

    cfg["access_token"] = access_token
    if refresh_token:
        cfg["refresh_token"] = refresh_token
    cfg["token_expiry"] = int(time.time()) + expires_in - 60
    cfg["accounts_url"] = accounts_url
    cfg.pop("code", None)  # consumed

    save_config(config_path, cfg)
    print("Tokens obtained and saved.")
    return access_token


# ---------------------------------------------------------------------------
# Token refresh — refresh_token → new access_token
# ---------------------------------------------------------------------------

def refresh_access_token(accounts_url: str, cfg: dict, config_path: Path) -> str | None:
    client_id = cfg.get("client_id")
    client_secret = cfg.get("client_secret")
    refresh_token = cfg.get("refresh_token")

    if not client_id or not client_secret:
        _die("client_id and client_secret are required in the config file.")
    if not refresh_token:
        return None

    print("Refreshing access token...")
    resp = requests.post(f"{accounts_url}/oauth/v2/token", data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }, timeout=30)

    data = resp.json()
    if "error" in data:
        err = data.get("error_description", data["error"])
        if "invalid_grant" in str(err).lower() or "invalid" in str(data.get("error", "")).lower():
            return None  # refresh token dead — caller should try auth code
        _die(f"Token refresh failed: {err}")

    access_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)

    cfg["access_token"] = access_token
    cfg["token_expiry"] = int(time.time()) + expires_in - 60
    save_config(config_path, cfg)
    print("Access token refreshed.")
    return access_token


# ---------------------------------------------------------------------------
# Get a valid token (full lifecycle)
# ---------------------------------------------------------------------------

def get_valid_token(workdrive_url: str | None, config_path: Path) -> str:
    """Return a valid access token.

    Resolution order (skips steps that can't apply):
    1. Cached access_token exists and not expired → return silently (no network)
    2. refresh_token exists → try refresh
    3. code exists in config → exchange auth code
    4. Raise error with instructions

    Never prints the token value.
    """
    cfg = load_config(config_path)
    accounts_url = detect_accounts_url(workdrive_url, cfg)

    # 1. Cached token still valid?
    access_token = cfg.get("access_token")
    expiry = cfg.get("token_expiry", 0)
    if access_token and time.time() < expiry:
        return access_token  # silent — no print, no network call

    # 2. Try refresh token
    if cfg.get("refresh_token"):
        new_token = refresh_access_token(accounts_url, cfg, config_path)
        if new_token:
            return new_token
        print("Refresh token invalid or expired, trying auth code...", file=sys.stderr)

    # 3. Try auth code exchange
    if cfg.get("code"):
        return exchange_auth_code(accounts_url, cfg, config_path)

    # 4. Nothing available
    _die(
        "No valid credentials. The config needs either:\n"
        "  - A valid 'code' (one-time auth code), or\n"
        "  - A valid 'refresh_token' (auto-saved from a previous run)\n\n"
        "Generate a new auth code:\n"
        "  1. Go to https://api-console.zoho.com/\n"
        "  2. Select your app → 'Generate Code'\n"
        "  3. Scopes: WorkDrive.files.READ, ZohoFiles.files.READ\n"
        f"  4. Paste into {config_path} as \"code\""
    )


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def extract_file_id(url_or_id: str) -> str:
    url_or_id = url_or_id.strip()
    if re.match(r'^[a-zA-Z0-9_]+$', url_or_id):
        return url_or_id

    try:
        parsed = urlparse(url_or_id)
    except Exception:
        return url_or_id

    match = re.search(r'/file/([a-zA-Z0-9_]+)', parsed.path)
    if match:
        return match.group(1)
    match = re.search(r'/folder/([a-zA-Z0-9_]+)', parsed.path)
    if match:
        return match.group(1)

    segments = [s for s in parsed.path.split('/') if s]
    return segments[-1] if segments else url_or_id


def get_api_base_url(url_or_id: str) -> str:
    try:
        host = urlparse(url_or_id).hostname or ""
    except Exception:
        host = ""

    for domain in ("zoho.in", "zoho.eu", "zoho.com.au", "zoho.jp", "zoho.com"):
        if domain in host:
            return f"https://workdrive.{domain}/api/v1"
    return "https://workdrive.zoho.in/api/v1"


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _auth_header(token: str) -> dict:
    return {"Authorization": f"Zoho-oauthtoken {token}"}


def get_file_info(api_base: str, file_id: str, token: str) -> dict:
    try:
        resp = requests.get(f"{api_base}/files/{file_id}", headers=_auth_header(token), timeout=30)
        if resp.status_code in (401, 404):
            return {}
        resp.raise_for_status()
        return resp.json().get("data", {}).get("attributes", {})
    except requests.RequestException:
        return {}


def get_download_url(api_base: str, file_id: str, token: str) -> str | None:
    """Get the direct download URL from file metadata.

    Zoho provides a pre-signed download_url in the file attributes.
    This is more reliable than the /download API endpoint.
    """
    info = get_file_info(api_base, file_id, token)
    return info.get("download_url")


def download_file(api_base: str, file_id: str, token: str, output_path: str | None = None) -> str:
    info = get_file_info(api_base, file_id, token)
    filename = info.get("name")
    if filename:
        print(f"File: {filename}")
    if info.get("size"):
        print(f"Size: {info['size'] / (1024 * 1024):.2f} MB")

    # Get the direct download URL from metadata (more reliable than API endpoint)
    download_url = info.get("download_url")
    if not download_url:
        download_url = f"{api_base}/files/{file_id}/download"

    print("Downloading...")
    resp = requests.get(
        download_url,
        headers=_auth_header(token),
        allow_redirects=True, timeout=300, stream=True,
    )

    if resp.status_code == 401:
        err_body = resp.text[:200]
        if "INVALID_OAUTHSCOPE" in err_body:
            _die(
                "Token missing download scope. Regenerate with BOTH scopes:\n"
                "  WorkDrive.files.READ, ZohoFiles.files.READ\n"
                "  1. Go to https://api-console.zoho.com/\n"
                "  2. Delete old token, generate new one with both scopes\n"
                "  3. Update ~/.zoho-workdrive.json with new code"
            )
        _die("Token rejected during download. Delete access_token from config and run again.")
    if resp.status_code == 404:
        _die(f"File not found: {file_id}")
    resp.raise_for_status()

    if not filename:
        cd = resp.headers.get("Content-Disposition", "")
        match = re.search(r'filename="?([^";]+)"?', cd)
        filename = match.group(1) if match else f"workdrive_{file_id}"

    if output_path:
        save_path = Path(output_path)
        if save_path.is_dir():
            save_path = save_path / filename
    else:
        save_path = Path(filename)

    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = (downloaded / total) * 100
                print(f"\r{pct:.1f}% ({downloaded:,}/{total:,} bytes)", end="", flush=True)
    print()
    return str(save_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download files from Zoho WorkDrive",
        epilog=(
            "Config (~/.zoho-workdrive.json):\n"
            '  {"client_id": "...", "client_secret": "...", "code": "..."}\n'
            "Tokens are auto-managed and written back to the config."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url_or_id", help="WorkDrive URL or bare file ID")
    parser.add_argument("--output", "-o", help="Output file path or directory", default=None)
    parser.add_argument("--config", "-c", help="Config file path", default=None)
    parser.add_argument("--base-url", help="Override API base URL", default=None)

    args = parser.parse_args()
    config_path = Path(args.config).expanduser() if args.config else DEFAULT_CONFIG

    token = get_valid_token(args.url_or_id, config_path)

    file_id = extract_file_id(args.url_or_id)
    api_base = args.base_url or get_api_base_url(args.url_or_id)
    print(f"File ID: {file_id}")

    saved_path = download_file(api_base, file_id, token, args.output)
    print(f"Saved to: {saved_path}")


if __name__ == "__main__":
    main()
