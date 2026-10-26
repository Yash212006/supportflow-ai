from __future__ import annotations

import os
from typing import Any

import httpx

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def get(path: str, params: dict | None = None) -> Any:
    with httpx.Client(timeout=60.0) as client:
        r = client.get(f"{API_BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()


def post(path: str, json: dict | None = None, files=None, timeout: float = 120.0) -> Any:
    with httpx.Client(timeout=timeout) as client:
        if files:
            r = client.post(f"{API_BASE}{path}", files=files, data=json)
        else:
            r = client.post(f"{API_BASE}{path}", json=json)
        r.raise_for_status()
        return r.json()


def put(path: str, json: dict | None = None) -> Any:
    with httpx.Client(timeout=60.0) as client:
        r = client.put(f"{API_BASE}{path}", json=json)
        r.raise_for_status()
        return r.json()


def delete(path: str) -> Any:
    with httpx.Client(timeout=60.0) as client:
        r = client.delete(f"{API_BASE}{path}")
        r.raise_for_status()
        return r.json()
