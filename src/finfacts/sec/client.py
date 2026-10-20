"""HTTP client for SEC EDGAR: rate-limited, retried, with the mandatory User-Agent."""

import logging
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from finfacts.sec.rate_limit import TokenBucket

log = logging.getLogger(__name__)

# SEC answers 403 when a client exceeds the fair-access threshold, so it is retryable too.
RETRYABLE_STATUS = frozenset({403, 429, 500, 502, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


_retry = retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential_jitter(initial=1, max=60),
    stop=stop_after_attempt(6),
    reraise=True,
)


class SecClient:
    def __init__(
        self,
        user_agent: str,
        max_rps: float = 8.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._bucket = TokenBucket(rate=max_rps)
        self._http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(30.0, read=120.0),
            follow_redirects=True,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._http.close()

    @_retry
    def get_json(self, url: str) -> Any:
        self._bucket.acquire()
        resp = self._http.get(url)
        resp.raise_for_status()
        return resp.json()

    @_retry
    def last_modified_date(self, url: str) -> str:
        """Return the Last-Modified header as YYYY-MM-DD (the SEC snapshot date)."""
        self._bucket.acquire()
        resp = self._http.head(url)
        resp.raise_for_status()
        return parsedate_to_datetime(resp.headers["Last-Modified"]).date().isoformat()

    @_retry
    def download(self, url: str, dest: Path) -> Path:
        """Stream ``url`` to ``dest`` atomically. Skips the download if ``dest`` exists."""
        if dest.exists():
            log.info("cached: %s", dest)
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        self._bucket.acquire()
        # identity encoding so Content-Length matches the bytes we write.
        with self._http.stream("GET", url, headers={"Accept-Encoding": "identity"}) as resp:
            resp.raise_for_status()
            expected = int(resp.headers.get("Content-Length", 0))
            with tmp.open("wb") as fh:
                for chunk in resp.iter_raw(chunk_size=1 << 20):
                    fh.write(chunk)
        if expected and tmp.stat().st_size != expected:
            tmp.unlink()
            raise httpx.TransportError(f"truncated download of {url}")
        tmp.replace(dest)
        log.info("downloaded: %s (%d bytes)", dest, dest.stat().st_size)
        return dest
