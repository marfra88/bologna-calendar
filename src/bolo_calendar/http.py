from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .lega_sdp import UpstreamError


USER_AGENT = "sports-calendar/1.0 (+https://github.com/marfra88/bologna-calendar)"


def get_json(url: str) -> Any:
    error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as caught:
            error = caught
            if attempt == 2:
                raise UpstreamError(f"Official source request failed: {caught}") from caught
            time.sleep(2**attempt)
    raise UpstreamError(f"Official source request failed: {error}")


def get_text(url: str) -> str:
    error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as caught:
            error = caught
            if attempt == 2:
                raise UpstreamError(f"Official source request failed: {caught}") from caught
            time.sleep(2**attempt)
    raise UpstreamError(f"Official source request failed: {error}")
