"""Long-lived APIMatic PayPal SDK client (sync), built from settings.

Per the APIMatic plugin guidance (python-client-initialization / python-authentication):
- one client per process, never rebuilt per request; closed on shutdown
- base_url always passed explicitly (omitting it silently selects sandbox)
- no client is built without credentials, so no request is ever sent unauthenticated
"""

from __future__ import annotations

import threading

from paypal import PaypalClient
from paypal.core import ClientCredentials, HttpClient

from app.core.config import get_settings
from app.integrations.paypal.errors import PayPalNotConfigured

_lock = threading.Lock()
_client: PaypalClient | None = None
_override_transport: HttpClient | None = None


def get_paypal_client() -> PaypalClient:
    global _client
    settings = get_settings()
    if not settings.paypal_configured:
        raise PayPalNotConfigured()
    if _client is None:
        with _lock:
            if _client is None:
                kwargs: dict[str, object] = {}
                if _override_transport is not None:
                    kwargs["custom_http_client"] = _override_transport
                    kwargs["retry_options"] = 0
                _client = PaypalClient(
                    base_url=settings.paypal_base_url,
                    timeout=settings.paypal_timeout_seconds,
                    oauth2=ClientCredentials(client_id=settings.paypal_client_id, client_secret=settings.paypal_client_secret),
                    **kwargs,  # type: ignore[arg-type]
                )
    return _client


def close_paypal_client() -> None:
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None


def use_transport_for_tests(transport: HttpClient | None) -> None:
    """Test seam (python-testing): inject a fake transport. Never used outside tests."""
    global _override_transport
    close_paypal_client()
    _override_transport = transport
