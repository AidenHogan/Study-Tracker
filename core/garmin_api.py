# file: core/garmin_api.py
"""
Client for the official Garmin Connect Developer Program **Health API**.

Replaces the unofficial `garth` library (which logged in with the user's Garmin email/password)
with Garmin's supported flow:

* **Auth:** OAuth 2.0 Authorization Code + PKCE. The user approves access in their browser on
  connect.garmin.com; a short-lived loopback HTTP server on localhost receives the redirect.
  Tokens (access ~24h, refresh ~90d) are stored locally and refreshed automatically.
* **Data:** Health API summary endpoints (dailies, sleeps, stressDetails, pulseox, respiration,
  hrv, userMetrics, skinTemp, bodyComps) pulled by *upload time* in <=24h windows, plus optional
  backfill requests for historical ranges.

Two ways to authenticate (choose in "Garmin -> Configure Garmin API"):

* **Personal API key** (GARMIN_API_KEY), created on Garmin Connect Web: no browser sign-in.
  The key is exchanged for a 24h access token and data is read from the Garmin Connect
  Personal API (date-based endpoints; see core/garmin_downloader.sync_personal_api).
* **Developer app (OAuth 2.0 PKCE)**: a Garmin Connect Developer Program app with the Health API
  enabled (GARMIN_CLIENT_ID, GARMIN_CLIENT_SECRET, GARMIN_REDIRECT_URI), then browser sign-in.

All endpoint URLs are module constants and may be overridden in the config file
(`authorize_url`, `token_url`, `api_base_url`) in case Garmin changes them.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timezone

import requests

# --- Endpoints (Garmin Connect Developer Program, OAuth2 PKCE + Health API) ---
AUTHORIZE_URL = "https://connect.garmin.com/oauth2Confirm"
TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token"
API_BASE_URL = "https://apis.garmin.com/wellness-api/rest"

DEFAULT_REDIRECT_URI = "http://localhost:8765/garmin/callback"

# Garmin limits pull requests to a 24 hour upload window and backfill requests to 90 days.
MAX_PULL_WINDOW_SECONDS = 86400
MAX_BACKFILL_WINDOW_SECONDS = 90 * 86400

# Summary types we pull. Key = endpoint path segment (also used for backfill).
SUMMARY_TYPES = (
    "dailies",
    "sleeps",
    "stressDetails",
    "pulseox",
    "respiration",
    "hrv",
    "userMetrics",
    "skinTemp",
    "bodyComps",
)

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".studytracker")
CONFIG_PATH = os.path.join(CONFIG_DIR, "garmin_api_config.json")
TOKEN_PATH = os.path.join(CONFIG_DIR, "garmin_api_token.json")
STATE_PATH = os.path.join(CONFIG_DIR, "garmin_api_state.json")

REQUEST_TIMEOUT = 30


class GarminAPIError(Exception):
    """Generic Garmin Health API failure (network, HTTP error, bad response)."""


class GarminAuthError(GarminAPIError):
    """Missing configuration, missing/expired authorization, or rejected credentials."""


class GarminConfigError(GarminAuthError):
    """The app's Garmin developer credentials (client id/secret) are not configured."""


# ---------------------------------------------------------------------------
# Small JSON file helpers
# ---------------------------------------------------------------------------

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)  # best effort; no-op on most Windows setups
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Configuration (developer app credentials)
# ---------------------------------------------------------------------------

AUTH_MODE_OAUTH = "oauth"
AUTH_MODE_API_KEY = "api_key"

# Garmin Connect Personal API (https://developer.garmin.com/gc-developer-program/personal/).
# The personal key is exchanged for a 24h OAuth2 access token (no refresh tokens):
#   POST {PERSONAL_TOKEN_URL}  with header  "Authorization: ApiKey <key>"
# and data is read from date-based Garmin Connect endpoints on PERSONAL_API_BASE_URL.
PERSONAL_API_BASE_URL = "https://personal.connectapi.garmin.com"
PERSONAL_TOKEN_URL = PERSONAL_API_BASE_URL + "/personalapitoken-service/personal-api/personal-api-key/token"
PERSONAL_TOKEN_LIFETIME = 24 * 3600


def load_config():
    """Return the effective config. Environment variables override the config file.

    Setting GARMIN_API_KEY selects personal-API-key mode unless GARMIN_AUTH_MODE says otherwise.
    """
    cfg = _read_json(CONFIG_PATH)
    env_map = {
        "client_id": "GARMIN_CLIENT_ID",
        "client_secret": "GARMIN_CLIENT_SECRET",
        "redirect_uri": "GARMIN_REDIRECT_URI",
        "api_key": "GARMIN_API_KEY",
        "auth_mode": "GARMIN_AUTH_MODE",
    }
    for key, env in env_map.items():
        if os.getenv(env):
            cfg[key] = os.getenv(env)
    if os.getenv("GARMIN_API_KEY") and not os.getenv("GARMIN_AUTH_MODE"):
        cfg["auth_mode"] = AUTH_MODE_API_KEY
    cfg.setdefault("auth_mode", AUTH_MODE_API_KEY if cfg.get("api_key") and not cfg.get("client_id")
                   else AUTH_MODE_OAUTH)
    cfg.setdefault("redirect_uri", DEFAULT_REDIRECT_URI)
    cfg.setdefault("authorize_url", AUTHORIZE_URL)
    cfg.setdefault("token_url", TOKEN_URL)
    cfg.setdefault("api_base_url", API_BASE_URL)
    cfg.setdefault("personal_api_base_url", PERSONAL_API_BASE_URL)
    cfg.setdefault("personal_token_url", PERSONAL_TOKEN_URL)
    return cfg


def save_config(client_id, client_secret, redirect_uri=None):
    """Save developer-app (OAuth) credentials and switch to OAuth mode."""
    cfg = _read_json(CONFIG_PATH)
    cfg["client_id"] = client_id.strip()
    cfg["client_secret"] = client_secret.strip()
    cfg["redirect_uri"] = (redirect_uri or DEFAULT_REDIRECT_URI).strip()
    cfg["auth_mode"] = AUTH_MODE_OAUTH
    _write_json(CONFIG_PATH, cfg)


def save_api_key(api_key):
    """Save a personal API key and switch to API-key mode (no browser sign-in needed)."""
    cfg = _read_json(CONFIG_PATH)
    cfg["api_key"] = api_key.strip()
    cfg["auth_mode"] = AUTH_MODE_API_KEY
    _write_json(CONFIG_PATH, cfg)


def clear_api_key():
    cfg = _read_json(CONFIG_PATH)
    cfg.pop("api_key", None)
    if cfg.get("auth_mode") == AUTH_MODE_API_KEY:
        cfg["auth_mode"] = AUTH_MODE_OAUTH
    _write_json(CONFIG_PATH, cfg)


def uses_api_key(cfg=None):
    return (cfg or load_config()).get("auth_mode") == AUTH_MODE_API_KEY


def is_configured():
    cfg = load_config()
    if uses_api_key(cfg):
        return bool(cfg.get("api_key"))
    return bool(cfg.get("client_id") and cfg.get("client_secret"))


def _require_config():
    cfg = load_config()
    if uses_api_key(cfg):
        if not cfg.get("api_key"):
            raise GarminConfigError(
                "No Garmin API key is configured. Use Garmin -> Configure Garmin API to enter it.")
        return cfg
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise GarminConfigError(
            "Garmin API is not configured. Use Garmin -> Configure Garmin API to enter your "
            "personal API key, or your developer app's Client ID and Client Secret.")
    return cfg


def _require_oauth_config():
    cfg = _require_config()
    if uses_api_key(cfg):
        raise GarminConfigError("Browser sign-in is only used with a developer app (Client ID/Secret); "
                                "a personal API key is used directly.")
    return cfg


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def load_token():
    return _read_json(TOKEN_PATH)


def _store_token(resp_json):
    now = time.time()
    token = {
        "access_token": resp_json["access_token"],
        "refresh_token": resp_json.get("refresh_token"),
        "token_type": resp_json.get("token_type", "bearer"),
        "scope": resp_json.get("scope"),
        "expires_at": now + int(resp_json.get("expires_in", 0)),
    }
    if resp_json.get("refresh_token_expires_in"):
        token["refresh_expires_at"] = now + int(resp_json["refresh_token_expires_in"])
    else:
        # keep the previous refresh expiry if the server did not return one
        old = load_token()
        if old.get("refresh_expires_at"):
            token["refresh_expires_at"] = old["refresh_expires_at"]
    _write_json(TOKEN_PATH, token)
    return token


def has_token():
    """True when requests can be authorized (a personal API key counts as always authorized)."""
    cfg = load_config()
    if uses_api_key(cfg):
        return bool(cfg.get("api_key"))
    tok = load_token()
    if not tok.get("access_token"):
        return False
    exp = tok.get("refresh_expires_at")
    return not (exp and exp < time.time())


def clear_token():
    for path in (TOKEN_PATH,):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _token_request(data):
    cfg = _require_oauth_config()
    payload = dict(data)
    payload["client_id"] = cfg["client_id"]
    payload["client_secret"] = cfg["client_secret"]
    try:
        resp = requests.post(cfg["token_url"], data=payload, timeout=REQUEST_TIMEOUT,
                             headers={"Accept": "application/json"})
    except requests.RequestException as e:
        raise GarminAPIError(f"Could not reach Garmin's token service: {e}") from e
    if resp.status_code in (400, 401, 403):
        raise GarminAuthError(f"Garmin rejected the authorization ({resp.status_code}): {resp.text[:300]}")
    if not resp.ok:
        raise GarminAPIError(f"Token request failed ({resp.status_code}): {resp.text[:300]}")
    try:
        return _store_token(resp.json())
    except (ValueError, KeyError) as e:
        raise GarminAPIError(f"Unexpected token response from Garmin: {resp.text[:300]}") from e


def refresh_access_token():
    tok = load_token()
    if not tok.get("refresh_token"):
        raise GarminAuthError("Not signed in to Garmin. Use Garmin -> Sign in to Garmin.")
    return _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})


def get_access_token():
    """Return a valid access token, refreshing it if it is (about to be) expired."""
    tok = load_token()
    if not tok.get("access_token"):
        raise GarminAuthError("Not signed in to Garmin. Use Garmin -> Sign in to Garmin.")
    if tok.get("refresh_expires_at") and tok["refresh_expires_at"] < time.time():
        raise GarminAuthError("Your Garmin authorization has expired. Please sign in to Garmin again.")
    if tok.get("expires_at", 0) - 120 < time.time():
        tok = refresh_access_token()
    return tok["access_token"]


# ---------------------------------------------------------------------------
# OAuth2 PKCE sign-in with loopback redirect
# ---------------------------------------------------------------------------

def _pkce_pair():
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(cfg, state, challenge):
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "redirect_uri": cfg["redirect_uri"],
        "state": state,
    }
    return f"{cfg['authorize_url']}?{urllib.parse.urlencode(params)}"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result = None  # set on the server instance

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != self.server.expected_path:
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        self.server.result = {k: v[0] for k, v in qs.items()}
        ok = "code" in self.server.result
        body = ("<h2>Garmin connected.</h2><p>You can close this window and return to Study Tracker.</p>"
                if ok else "<h2>Garmin sign-in was not completed.</h2><p>You can close this window.</p>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):  # keep the console quiet
        pass


def authorize_interactive(timeout=300, on_tick=None, open_browser=True):
    """Run the full OAuth2 PKCE sign-in.

    Opens the user's browser at Garmin's consent page and waits for the redirect on the
    configured localhost redirect URI. `on_tick` (e.g. a Tk `update` function) is called
    regularly while waiting so the GUI stays responsive.

    Returns the stored token dict. Raises GarminAuthError on failure/timeout.
    """
    cfg = _require_oauth_config()
    redirect = urllib.parse.urlparse(cfg["redirect_uri"])
    if redirect.hostname not in ("localhost", "127.0.0.1") or not redirect.port:
        raise GarminConfigError(
            f"Redirect URI must be a localhost URL with a port (e.g. {DEFAULT_REDIRECT_URI}); "
            f"got {cfg['redirect_uri']}. It must also be registered on your Garmin developer app.")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)

    socketserver.TCPServer.allow_reuse_address = True
    try:
        server = http.server.HTTPServer(("127.0.0.1", redirect.port), _CallbackHandler)
    except OSError as e:
        raise GarminAuthError(f"Could not listen on port {redirect.port} for the Garmin redirect: {e}") from e
    server.expected_path = redirect.path or "/"
    server.result = None
    server.timeout = 0.25

    url = build_authorize_url(cfg, state, challenge)
    try:
        if open_browser:
            webbrowser.open(url)
        else:
            print("Open this URL to authorize Garmin access:\n", url)
        deadline = time.time() + timeout
        while server.result is None and time.time() < deadline:
            server.handle_request()
            if on_tick:
                on_tick()
    finally:
        server.server_close()

    result = server.result
    if result is None:
        raise GarminAuthError("Timed out waiting for Garmin sign-in to complete in the browser.")
    if result.get("state") != state:
        raise GarminAuthError("Garmin sign-in failed: state mismatch (possible stale or forged redirect).")
    if "code" not in result:
        raise GarminAuthError(f"Garmin sign-in was declined or failed: {result.get('error', 'unknown error')}")

    return _token_request({
        "grant_type": "authorization_code",
        "code": result["code"],
        "code_verifier": verifier,
        "redirect_uri": cfg["redirect_uri"],
    })


# ---------------------------------------------------------------------------
# Health API requests
# ---------------------------------------------------------------------------

def _parse_personal_token(resp):
    """The token endpoint's response shape isn't documented; accept the common variants."""
    try:
        data = resp.json()
    except ValueError:
        data = resp.text.strip().strip('"')
    if isinstance(data, str):
        return data, PERSONAL_TOKEN_LIFETIME
    if isinstance(data, dict):
        for key in ("access_token", "accessToken", "token"):
            if isinstance(data.get(key), str) and data[key]:
                lifetime = data.get("expires_in") or data.get("expiresIn") or PERSONAL_TOKEN_LIFETIME
                try:
                    lifetime = int(lifetime)
                except (TypeError, ValueError):
                    lifetime = PERSONAL_TOKEN_LIFETIME
                return data[key], lifetime
    raise GarminAPIError("Unexpected response from Garmin's personal token endpoint "
                         f"(fields: {', '.join(data) if isinstance(data, dict) else type(data).__name__}).")


def get_personal_access_token(force_new=False):
    """Exchange the personal API key for an access token (cached until shortly before expiry)."""
    cfg = _require_config()
    tok = load_token().get("personal") or {}
    if not force_new and tok.get("access_token") and tok.get("expires_at", 0) - 300 > time.time():
        return tok["access_token"]
    try:
        resp = requests.post(cfg["personal_token_url"], timeout=REQUEST_TIMEOUT,
                             # No Accept header: the endpoint returns the token as text/plain and
                             # answers "Accept: application/json" with 406 Not Acceptable.
                             headers={"Authorization": f"ApiKey {cfg['api_key']}"})
    except requests.RequestException as e:
        raise GarminAPIError(f"Could not reach Garmin's personal token service: {e}") from e
    if resp.status_code in (400, 401, 403):
        raise GarminAuthError(
            f"Garmin rejected the personal API key ({resp.status_code}). Check that it was copied correctly "
            f"and has not expired or been deleted on Garmin Connect. {resp.text[:200]}")
    if not resp.ok:
        raise GarminAPIError(f"Personal token request failed ({resp.status_code}): {resp.text[:200]}")
    access_token, lifetime = _parse_personal_token(resp)
    all_tokens = load_token()
    all_tokens["personal"] = {"access_token": access_token, "expires_at": time.time() + lifetime}
    _write_json(TOKEN_PATH, all_tokens)
    return access_token


def personal_get(path, params=None, retry_auth=True):
    """GET a Garmin Connect Personal API endpoint. Returns parsed JSON (None for 204/empty)."""
    cfg = _require_config()
    url = f"{cfg['personal_api_base_url'].rstrip('/')}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {get_personal_access_token(force_new=not retry_auth)}",
               "Accept": "application/json"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        raise GarminAPIError(f"Network error contacting Garmin: {e}") from e
    if resp.status_code == 401 and retry_auth:
        return personal_get(path, params, retry_auth=False)  # token expired early -> get a new one
    if resp.status_code in (401, 403):
        raise GarminAuthError(f"Garmin denied access to '{path}' ({resp.status_code}). {resp.text[:200]}")
    if resp.status_code in (204, 404):
        return None
    if not resp.ok:
        raise GarminAPIError(f"Garmin returned {resp.status_code} for {path}: {resp.text[:200]}")
    return resp.json() if resp.content else None


def verify_credentials():
    """Cheap check that the configured credentials work. Returns a short description."""
    if uses_api_key():
        get_personal_access_token(force_new=True)
        personal_get("userprofile-service/userprofile/settings")
        return "Garmin accepted the personal API key."
    return f"Connected as Garmin user {get_user_id()}."


def _api_get(path, params=None, retry_auth=True):
    """GET a Health API (developer program) endpoint."""
    cfg = _require_oauth_config()
    url = f"{cfg['api_base_url'].rstrip('/')}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {get_access_token()}", "Accept": "application/json"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        raise GarminAPIError(f"Network error contacting Garmin: {e}") from e

    if resp.status_code == 401 and retry_auth:
        refresh_access_token()
        return _api_get(path, params, retry_auth=False)
    if resp.status_code in (401, 403):
        raise GarminAuthError(
            f"Garmin denied access to '{path}' ({resp.status_code}). The user may have revoked access "
            f"or not granted this permission. {resp.text[:200]}")
    return resp


def get_user_id():
    resp = _api_get("user/id")
    if not resp.ok:
        raise GarminAPIError(f"Could not read Garmin user id ({resp.status_code}): {resp.text[:200]}")
    return resp.json().get("userId")


def get_user_permissions():
    """Return the list of permissions the user granted (e.g. HEALTH_EXPORT)."""
    resp = _api_get("user/permissions")
    if not resp.ok:
        return []
    data = resp.json()
    return data if isinstance(data, list) else data.get("permissions", [])


def deregister_user():
    """Revoke this app's access for the signed-in user and forget local tokens.
    In API-key mode this only removes the stored key (revoke the key itself on Garmin's site)."""
    if uses_api_key():
        clear_api_key()
        clear_token()
        return
    try:
        cfg = _require_config()
        url = f"{cfg['api_base_url'].rstrip('/')}/user/registration"
        requests.delete(url, headers={"Authorization": f"Bearer {get_access_token()}"}, timeout=REQUEST_TIMEOUT)
    except GarminAPIError:
        pass
    finally:
        clear_token()


def pull_summaries(summary_type, upload_start, upload_end, log=print):
    """Pull one summary type for an upload-time range, chunked into <=24h windows.

    `upload_start` / `upload_end` are unix epoch seconds. Returns a list of summary dicts.
    Endpoints the user has not granted / the app is not enabled for are skipped (empty list).
    """
    out = []
    start = int(upload_start)
    end = int(upload_end)
    while start < end:
        chunk_end = min(start + MAX_PULL_WINDOW_SECONDS, end)
        resp = _api_get(summary_type, {
            "uploadStartTimeInSeconds": start,
            "uploadEndTimeInSeconds": chunk_end,
        })
        if resp.status_code in (404, 405):
            log(f"   -> '{summary_type}' is not available for this Garmin app; skipping.")
            return out
        if resp.status_code == 400:
            # Most commonly: window outside the range Garmin keeps available for pull.
            log(f"   -> Garmin refused {summary_type} window "
                f"{_fmt_ts(start)}..{_fmt_ts(chunk_end)}: {resp.text[:200]}")
        elif not resp.ok:
            raise GarminAPIError(f"Garmin returned {resp.status_code} for {summary_type}: {resp.text[:200]}")
        else:
            data = resp.json() if resp.content else []
            if isinstance(data, dict):  # defensive: some responses wrap the list
                data = data.get(summary_type, []) or data.get("summaries", [])
            out.extend(data or [])
        start = chunk_end
    return out


def request_backfill(summary_type, start_ts, end_ts):
    """Ask Garmin to (re)deliver historical summaries for a summary-time range (<= 90 days per call).

    Backfill is asynchronous: the data becomes available to `pull_summaries` with an upload time
    of roughly "now" once Garmin has processed the request. Returns the number of accepted requests.
    """
    accepted = 0
    start, end = int(start_ts), int(end_ts)
    while start < end:
        chunk_end = min(start + MAX_BACKFILL_WINDOW_SECONDS, end)
        resp = _api_get(f"backfill/{summary_type}", {
            "summaryStartTimeInSeconds": start,
            "summaryEndTimeInSeconds": chunk_end,
        })
        # 202 Accepted = queued; 409 = an identical backfill was already requested.
        if resp.status_code in (200, 202, 409):
            accepted += 1
        start = chunk_end
    return accepted


def _fmt_ts(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------------------------------------
# Sync state (last upload window successfully pulled)
# ---------------------------------------------------------------------------

def load_state():
    return _read_json(STATE_PATH)


def save_state(**updates):
    st = load_state()
    st.update(updates)
    _write_json(STATE_PATH, st)
