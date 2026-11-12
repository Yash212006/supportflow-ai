"""Single error boundary for the APIMatic PayPal SDK (see paypal-plan.md, "Error boundary").

Every SDK call goes through `call_paypal`, which converts the SDK's four failure kinds into
`PayPalError` with an explicit `outcome`:
- "not_sent": nothing reached PayPal (config/auth failure, connection refused)
- "rejected": PayPal answered with an error status, nothing happened
- "unknown": the request may have reached PayPal; the caller must reconcile, never assume success
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

import httpx2
import pydantic
from paypal.core import ApiError, OAuthProviderError, RawError, UnsetType
from paypal.models import Error as PayPalErrorBody

log = logging.getLogger("supportflow.paypal")

Outcome = Literal["not_sent", "rejected", "unknown"]
T = TypeVar("T")


@dataclass
class PayPalError(Exception):
    kind: str  # auth | api | transport | decode | not_configured
    message: str
    outcome: Outcome
    status_code: int | None = None
    name: str | None = None
    debug_id: str | None = None
    details: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        bits = [self.kind, self.message]
        if self.status_code:
            bits.append(f"HTTP {self.status_code}")
        if self.name:
            bits.append(self.name)
        issues = self.issues()
        if issues:
            bits.append("issue: " + ", ".join(issues))
        if self.debug_id:
            bits.append(f"debug_id={self.debug_id}")
        return " | ".join(bits)

    def issues(self) -> list[str]:
        """PayPal's machine-readable issue codes, e.g. CURRENCY_NOT_SUPPORTED."""
        return [str(d["issue"]) for d in self.details if d.get("issue")]

    def user_message(self) -> str:
        """Message for the UI: PayPal's message plus its issue code and description when present."""
        parts = [self.message]
        for d in self.details[:2]:
            if d.get("issue"):
                parts.append(f"{d['issue']}: {d.get('description') or ''}".strip().rstrip(":"))
        msg = " ".join(p.rstrip(".") + "." for p in parts if p)
        if any("CURRENCY" in i for i in self.issues()):
            msg += " Your PayPal Sandbox account does not accept this currency; set DEMO_CURRENCY=USD and re-seed with --reset."
        return msg

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "outcome": self.outcome,
            "status_code": self.status_code,
            "name": self.name,
            "debug_id": self.debug_id,
            "details": self.details,
        }


class PayPalNotConfigured(PayPalError):
    def __init__(self) -> None:
        super().__init__(
            kind="not_configured",
            message="PayPal Sandbox is not configured. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET.",
            outcome="not_sent",
        )


def _plain(v: Any) -> Any:
    """UNSET -> None, open enums -> their string value (python-models: Optional is UNSET, not None)."""
    if v is None or isinstance(v, UnsetType):
        return None
    return getattr(v, "value", v) if not isinstance(v, (str, int, float)) else v


_NOT_SENT = (httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout, httpx2.ProxyError)


def call_paypal(fn: Callable[[], T], *, is_write: bool) -> T:
    """Run one SDK call through the documented catch ladder."""
    try:
        return fn()
    except ApiError as e:
        err = e.error
        # 1. failed token fetch: configuration fault, nothing was attempted
        if isinstance(err, OAuthProviderError):
            raise PayPalError(
                kind="auth",
                message=f"PayPal OAuth token request failed: {err.error}"
                + (f" ({err.error_description})" if err.error_description else ""),
                outcome="not_sent",
                status_code=e.status_code,
            ) from e
        # 2. typed PayPal error body
        if isinstance(err, PayPalErrorBody):
            details: list[dict[str, Any]] = []
            raw_details = err.details if isinstance(err.details, list) else []
            for d in raw_details:
                details.append({k: _plain(getattr(d, k, None)) for k in ("issue", "description", "field")})
            raise PayPalError(
                kind="api",
                message=str(_plain(err.message) or "PayPal error"),
                outcome="rejected" if e.status_code < 500 or not is_write else "unknown",
                status_code=e.status_code,
                name=_plain(err.name),
                debug_id=_plain(err.debug_id),
                details=details,
            ) from e
        # 3. undocumented / raw body
        text = err.text()[:500] if isinstance(err, RawError) else str(type(err).__name__)
        raise PayPalError(
            kind="api",
            message=f"PayPal returned HTTP {e.status_code}: {text}",
            outcome="unknown" if (is_write and e.status_code >= 500) else "rejected",
            status_code=e.status_code,
        ) from e
    except _NOT_SENT as e:
        raise PayPalError(kind="transport", message=f"Could not reach PayPal: {type(e).__name__}", outcome="not_sent") from e
    except httpx2.RequestError as e:
        raise PayPalError(
            kind="transport",
            message=f"PayPal request interrupted after sending: {type(e).__name__}",
            outcome="unknown" if is_write else "not_sent",
        ) from e
    except (pydantic.ValidationError, ValueError) as e:
        raise PayPalError(
            kind="decode",
            message="PayPal response could not be decoded",
            outcome="unknown" if is_write else "rejected",
        ) from e
