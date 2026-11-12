"""Stub transport for the APIMatic PayPal SDK (python-testing skill: fake the transport, not the client)."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from paypal.core import HttpRequest, HttpResponse


@dataclass
class StubResponse:
    status_code: int = 200
    headers: Mapping[str, str] = field(default_factory=dict)
    chunks: list[bytes] = field(default_factory=list)
    url: str = "https://api.test/resource"
    closed: bool = False

    def iter_bytes(self, chunk_size: int | None) -> Iterator[bytes]:
        yield from self.chunks
        self.close()

    def read(self) -> bytes:
        self.close()
        return b"".join(self.chunks)

    def close(self) -> None:
        self.closed = True


class StubTransport:
    def __init__(self, *responses: StubResponse) -> None:
        self._responses = list(responses)
        self.requests: list[HttpRequest] = []
        self.error: Exception | None = None

    def queue(self, *responses: StubResponse) -> None:
        self._responses.extend(responses)

    def fail_next_with(self, error: Exception) -> None:
        self.error = error

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if self._responses:
            return self._responses.pop(0)  # type: ignore[return-value]
        if self.error is not None:
            err, self.error = self.error, None
            raise err
        raise AssertionError(f"Unexpected PayPal request in test: {request.method} {request.url}")

    def close(self) -> None: ...

    @property
    def operation_requests(self) -> list[HttpRequest]:
        return [r for r in self.requests if "/v1/oauth2/token" not in r.url]


def json_response(status: int, body: object) -> StubResponse:
    return StubResponse(status_code=status, headers={"content-type": "application/json"}, chunks=[json.dumps(body).encode()])


def token_response() -> StubResponse:
    return json_response(200, {"access_token": "t", "token_type": "Bearer", "expires_in": 3600})
