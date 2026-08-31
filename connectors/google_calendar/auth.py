"""
Google OAuth2 authentication for desktop applications.

Implements the Google-recommended OAuth 2.0 flow for installed/desktop apps:
1. Load client credentials from a local JSON file
2. Run a local HTTP server to receive the OAuth callback
3. Exchange the authorization code for tokens
4. Store tokens locally (encrypted at rest in the future)

The developer must provide their own credentials.json file from Google Cloud Console.
See docs/GOOGLE_CALENDAR_SETUP.md for setup instructions.
"""

import json
import logging
import threading
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Where to find the Google OAuth client credentials
CREDENTIALS_DIR = PROJECT_ROOT / "secrets"
CREDENTIALS_FILE = CREDENTIALS_DIR / "google_credentials.json"

# Where to persist the OAuth token locally
TOKEN_DIR = CREDENTIALS_DIR
TOKEN_FILE = TOKEN_DIR / "google_calendar_token.json"

# OAuth scopes — narrowest useful scope for reading calendar events
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Local server port for OAuth callback
OAUTH_PORT = 8090


def get_credentials_path() -> Path:
    """Return the path to the Google OAuth client credentials file."""
    return CREDENTIALS_FILE


def get_token_path() -> Path:
    """Return the path where the OAuth token is stored."""
    return TOKEN_FILE


def has_credentials() -> bool:
    """Check if the developer has placed their Google credentials file."""
    return CREDENTIALS_FILE.exists()


def has_valid_token() -> bool:
    """Check if a stored token exists and is potentially valid.

    This doesn't verify the token — it just checks if one is stored.
    Actual validity is checked by the service layer when making API calls.
    """
    return TOKEN_FILE.exists()


def load_stored_token() -> dict[str, Any] | None:
    """Load the stored OAuth token from disk.

    Returns:
        Token dict or None if not found/invalid.
    """
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load token: {e}")
        return None


def store_token(token_data: dict[str, Any]) -> bool:
    """Persist the OAuth token to disk.

    Args:
        token_data: Token data from Google's token exchange.

    Returns:
        True if stored successfully.
    """
    try:
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(
            json.dumps(token_data, indent=2, default=str),
            encoding="utf-8",
        )
        # Restrict file permissions on Unix (token contains secrets)
        try:
            import stat

            TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        except (OSError, AttributeError):
            pass  # Windows doesn't support chmod the same way
        logger.info("OAuth token stored successfully")
        return True
    except OSError as e:
        logger.error(f"Failed to store token: {e}")
        return False


def delete_token() -> bool:
    """Remove the stored OAuth token."""
    try:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
            logger.info("OAuth token deleted")
        return True
    except OSError as e:
        logger.error(f"Failed to delete token: {e}")
        return False


class OAuthCallbackHandler:
    """Handles the OAuth2 callback on a local HTTP server.

    This implements Google's recommended desktop OAuth flow:
    1. Start a temporary local HTTP server
    2. Open the browser to Google's authorization URL
    3. Wait for Google to redirect back with the auth code
    4. Exchange the code for tokens
    5. Shut down the temporary server
    """

    def __init__(self, port: int = OAUTH_PORT):
        self.port = port
        self._auth_code: str | None = None
        self._auth_error: str | None = None
        self._event = threading.Event()

    def get_redirect_uri(self) -> str:
        """Get the OAuth redirect URI for the local server."""
        return f"http://localhost:{self.port}"

    def start_server_and_wait(self, timeout: int = 120) -> tuple[str | None, str | None]:
        """Start the local callback server and wait for the OAuth response.

        Args:
            timeout: Maximum seconds to wait for the callback.

        Returns:
            Tuple of (auth_code, error_message). One will be None.
        """
        from http.server import HTTPServer, BaseHTTPRequestHandler

        handler_class = self._make_handler()

        try:
            server = HTTPServer(("localhost", self.port), handler_class)
            server.timeout = 1
        except OSError as e:
            return None, f"Could not start local server on port {self.port}: {e}"

        logger.info(f"OAuth callback server listening on port {self.port}")

        # Wait for the callback
        elapsed = 0
        while elapsed < timeout and not self._event.is_set():
            server.handle_request()
            elapsed += 1

        server.server_close()

        if not self._event.is_set():
            return None, "OAuth callback timed out"

        return self._auth_code, self._auth_error

    def _make_handler(self):
        """Create an HTTP request handler class with captured state."""
        parent = self

        class OAuthCallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)

                if "code" in params:
                    parent._auth_code = params["code"][0]
                    parent._event.set()
                    self._send_response(
                        "Authorization successful! You can close this window and return to Sarthi."
                    )
                elif "error" in params:
                    parent._auth_error = params["error"][0]
                    parent._event.set()
                    self._send_response(f"Authorization failed: {params['error'][0]}")
                else:
                    self._send_response("Waiting for authorization...")

            def _send_response(self, message: str):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                html = f"""
                <html><body style="font-family: Inter, sans-serif; background: #090909; color: #e5e2e1;
                display: flex; align-items: center; justify-content: center; height: 100vh;">
                <div style="text-align: center; max-width: 400px;">
                    <h2 style="color: #00d9ff;">Sarthi</h2>
                    <p>{message}</p>
                </div>
                </body></html>
                """
                self.wfile.write(html.encode())

            def log_message(self, format, *args):
                pass  # Suppress request logging

        return OAuthCallbackHandler


def build_auth_url(client_config: dict) -> tuple[str, str]:
    """Build the Google OAuth2 authorization URL.

    Args:
        client_config: The client credentials dict (from credentials.json).

    Returns:
        Tuple of (auth_url, state) where state can be used to verify the callback.
    """
    # Extract client info from the credentials file
    # Google credentials.json has "installed" or "web" key with client_id inside
    client_info = client_config.get("installed") or client_config.get("web", {})
    client_id = client_info.get("client_id", "")
    redirect_uri = OAuthCallbackHandler().get_redirect_uri()

    # Build the authorization URL manually (no google-auth dependency needed)
    import secrets as _secrets

    state = _secrets.token_urlsafe(16)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    return auth_url, state


def exchange_code(code: str, client_config: dict) -> dict[str, Any]:
    """Exchange an authorization code for tokens.

    Args:
        code: The authorization code from the OAuth callback.
        client_config: The client credentials dict.

    Returns:
        Dict with token data or error.
    """
    import httpx

    client_info = client_config.get("installed") or client_config.get("web", {})

    data = {
        "code": code,
        "client_id": client_info.get("client_id", ""),
        "client_secret": client_info.get("client_secret", ""),
        "redirect_uri": OAuthCallbackHandler().get_redirect_uri(),
        "grant_type": "authorization_code",
    }

    try:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data=data,
            timeout=30,
        )
        resp.raise_for_status()
        token_data = resp.json()
        # Store the token
        store_token(token_data)
        return {"success": True, "token": token_data}
    except httpx.HTTPStatusError as e:
        logger.error(f"Token exchange failed: {e.response.status_code} {e.response.text}")
        return {"success": False, "error": f"Token exchange failed: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Token exchange error: {e}")
        return {"success": False, "error": str(e)}


def refresh_token(client_config: dict) -> dict[str, Any] | None:
    """Refresh an expired access token using the stored refresh token.

    Args:
        client_config: The client credentials dict.

    Returns:
        Updated token dict or None if refresh failed.
    """
    import httpx

    token_data = load_stored_token()
    if not token_data or "refresh_token" not in token_data:
        return None

    client_info = client_config.get("installed") or client_config.get("web", {})

    data = {
        "client_id": client_info.get("client_id", ""),
        "client_secret": client_info.get("client_secret", ""),
        "refresh_token": token_data["refresh_token"],
        "grant_type": "refresh_token",
    }

    try:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data=data,
            timeout=30,
        )
        resp.raise_for_status()
        new_token = resp.json()
        # Merge with existing token (keep refresh_token)
        new_token.setdefault("refresh_token", token_data["refresh_token"])
        store_token(new_token)
        return new_token
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return None


def get_valid_credentials(client_config: dict) -> dict[str, Any] | None:
    """Get valid credentials, refreshing if necessary.

    Args:
        client_config: The client credentials dict.

    Returns:
        Valid token dict or None if authentication is not possible.
    """
    import time

    token_data = load_stored_token()
    if not token_data:
        return None

    # Check if token is expired (with 60-second buffer)
    expires_at = token_data.get("expires_at", 0)
    if isinstance(expires_at, str):
        try:
            from datetime import datetime

            expires_at = datetime.fromisoformat(expires_at).timestamp()
        except (ValueError, TypeError):
            expires_at = 0

    now = time.time()
    if expires_at and now >= (expires_at - 60):
        # Token expired, try to refresh
        refreshed = refresh_token(client_config)
        if refreshed:
            return refreshed
        return None

    return token_data
