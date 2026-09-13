"""
Web-interface Google connect — runs the OAuth2 consent flow inside Sarthi's
own automation browser (the Browser Awareness driver session).

Why: the default flow (connector.connect) opens the user's system default
browser and catches the redirect on a local callback server. The
web-interface flow instead opens Google's consent page in the automation
Chrome window — the same persistent-profile browser the automation uses —
so the Google sign-in happens in a visible, Sarthi-controlled window and
the login itself persists in the automation profile for future runs.

Flow:
    1. Start the local callback server (localhost:8090) in a background
       thread — it must be listening before Google redirects back.
    2. Open the automation Chrome at Google's authorization URL. The user
       signs in and consents in that window.
    3. Google redirects the tab to the callback server, which captures the
       authorization code.
    4. Exchange the code for tokens (stored exactly as in the desktop flow)
       and close the automation session — the Google login stays in the
       automation profile for later browser runs.
"""

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# The user signs in by hand in the automation window — allow more time than
# the desktop flow's 120 s callback wait.
WEB_FLOW_TIMEOUT_SECONDS = 300


def connect_via_web_interface(client_config: dict) -> dict[str, Any]:
    """Run the Google OAuth2 consent flow in the automation browser.

    Args:
        client_config: Google OAuth client credentials (credentials.json).

    Returns:
        Dict with success status, token data on success, error message
        otherwise — the same shape as the desktop connect flow.
    """
    from connectors.google_calendar.auth import (
        OAuthCallbackHandler,
        build_auth_url,
        exchange_code,
    )
    from skills.browser_awareness.driver import open_session

    auth_url, _state = build_auth_url(client_config)

    handler = OAuthCallbackHandler()
    result: dict[str, str | None] = {"code": None, "error": None}

    def _wait_for_callback() -> None:
        result["code"], result["error"] = handler.start_server_and_wait(
            timeout=WEB_FLOW_TIMEOUT_SECONDS
        )

    # The callback server runs in a background thread so this thread can
    # drive the browser while it listens for Google's redirect.
    waiter = threading.Thread(target=_wait_for_callback, daemon=True)
    waiter.start()

    # The web-interface flow exists so the user can interact with the
    # window — force it visible even when headless is configured.
    headless_saved = os.environ.get("BROWSER_AWARENESS_HEADLESS")
    os.environ.pop("BROWSER_AWARENESS_HEADLESS", None)
    session = None
    try:
        session = open_session(auth_url)
    except Exception as e:
        logger.error(f"Could not open the automation browser for Google sign-in: {e}")
        return {
            "success": False,
            "error": (
                "Could not open the automation browser for Google sign-in. "
                f"Original error: {e}"
            ),
        }
    finally:
        if headless_saved is not None:
            os.environ["BROWSER_AWARENESS_HEADLESS"] = headless_saved

    try:
        waiter.join(timeout=WEB_FLOW_TIMEOUT_SECONDS + 15)
    finally:
        # Close only after the flow finished (or timed out) — never while
        # the user is mid-sign-in.
        try:
            session.close()
        except Exception:  # pragma: no cover - live browser
            logger.debug("automation session close failed")

    error = result.get("error")
    if error:
        return {"success": False, "error": error}

    code = result.get("code")
    if not code:
        return {"success": False, "error": "Google sign-in was not completed in time"}

    return exchange_code(code, client_config)
