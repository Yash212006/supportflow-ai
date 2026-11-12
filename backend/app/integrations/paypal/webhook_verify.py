"""PayPal webhook signature verification.

The APIMatic PayPal SDK (v2.29) has no webhook-verification operation, so this module calls PayPal's
documented `POST /v1/notifications/verify-webhook-signature` directly. Only a
`verification_status == "SUCCESS"` answer from PayPal is accepted; every other outcome (missing headers,
missing webhook id, PayPal unreachable, FAILURE) means the event is NOT trusted.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

REQUIRED_HEADERS = (
    "paypal-auth-algo",
    "paypal-cert-url",
    "paypal-transmission-id",
    "paypal-transmission-sig",
    "paypal-transmission-time",
)


@dataclass
class VerificationResult:
    verified: bool
    status: str  # SUCCESS | FAILURE | MISSING_HEADERS | NOT_CONFIGURED | ERROR
    detail: str = ""


class _TokenCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at = 0.0

    def get(self, client: httpx.Client) -> str:
        with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            s = get_settings()
            resp = client.post(
                f"{s.paypal_base_url}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(s.paypal_client_id, s.paypal_client_secret),
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            body = resp.json()
            self._token = str(body["access_token"])
            self._expires_at = time.time() + float(body.get("expires_in", 300))
            return self._token


_tokens = _TokenCache()


def verify_webhook(headers: Mapping[str, str], event: dict[str, Any], *, http: httpx.Client | None = None) -> VerificationResult:
    s = get_settings()
    if not s.paypal_webhook_configured:
        return VerificationResult(False, "NOT_CONFIGURED", "PAYPAL_WEBHOOK_ID / credentials not set; event not trusted")
    lower = {k.lower(): v for k, v in headers.items()}
    missing = [h for h in REQUIRED_HEADERS if not lower.get(h)]
    if missing:
        return VerificationResult(False, "MISSING_HEADERS", f"missing: {', '.join(missing)}")
    body = {
        "auth_algo": lower["paypal-auth-algo"],
        "cert_url": lower["paypal-cert-url"],
        "transmission_id": lower["paypal-transmission-id"],
        "transmission_sig": lower["paypal-transmission-sig"],
        "transmission_time": lower["paypal-transmission-time"],
        "webhook_id": s.paypal_webhook_id,
        "webhook_event": event,
    }
    own = http is None
    client = http or httpx.Client(timeout=s.paypal_timeout_seconds)
    try:
        token = _tokens.get(client)
        resp = client.post(
            f"{s.paypal_base_url}/v1/notifications/verify-webhook-signature",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            return VerificationResult(False, "ERROR", f"verify endpoint HTTP {resp.status_code}")
        status = str(resp.json().get("verification_status", "FAILURE"))
        return VerificationResult(status == "SUCCESS", status)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        return VerificationResult(False, "ERROR", type(exc).__name__)
    finally:
        if own:
            client.close()
